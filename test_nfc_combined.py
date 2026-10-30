"""Host-side tests: python -m unittest test_nfc_combined.py."""

import sys
import unittest
from unittest.mock import patch

from nfc_combined import NFCReader, create_ndef_text_payload, parse_ndef_text
import tag_manager


class FakeClock:
    @staticmethod
    def sleep_ms(duration):
        pass


class FakeReader:
    OK = 0

    def __init__(self, capacity=144):
        self.memory = bytearray(16 + capacity)
        self.memory[12:16] = bytes([0xE1, 0x10, capacity // 8, 0])
        self.writes = []
        self.ack = 0x0A
        self.corrupt_readback = False

    def _cflags(self, register, mask):
        pass

    def _crc(self, command):
        return [0, 0]

    def _tocard(self, command, frame):
        page = frame[1]
        if frame[0] == 0x30:
            data = list(self.memory[page * 4:page * 4 + 16])
            if self.corrupt_readback and self.writes and page >= 4:
                data[0] ^= 1
            return self.OK, data, len(data) * 8
        self.writes.append(page)
        self.memory[page * 4:page * 4 + 4] = bytes(frame[2:6])
        return self.OK, [self.ack], 4


def make_nfc(capacity=144):
    nfc = NFCReader.__new__(NFCReader)
    nfc.reader = FakeReader(capacity)
    return nfc


class TextTests(unittest.TestCase):
    def test_round_trip(self):
        for text in ("", "Hello from Raspberry Pi Pico!", "caf\u00e9", "T\x00\xfe"):
            with self.subTest(text=text):
                self.assertEqual(parse_ndef_text(create_ndef_text_payload(text)), text)

    def test_padding_and_other_tlv(self):
        payload = b"\x00\x01\x02TT" + create_ndef_text_payload("hello") + b"old"
        self.assertEqual(parse_ndef_text(payload), "hello")
        self.assertIsNone(parse_ndef_text(b"\x00\xfe"))

    def test_extended_tlv_and_long_record(self):
        body = b"\x02enhello"
        record = b"\xc1\x01" + len(body).to_bytes(4, "big") + b"T" + body
        raw = b"\x03\xff" + len(record).to_bytes(2, "big") + record + b"\xfe"
        self.assertEqual(parse_ndef_text(raw), "hello")

    def test_limits(self):
        self.assertEqual(len(create_ndef_text_payload("x" * 247)), 257)
        for text, language in (("x" * 248, "en"), ("hello", ""), ("", "x" * 64)):
            with self.assertRaises(ValueError):
                create_ndef_text_payload(text, language)

    def test_truncated_data(self):
        for raw in (b"\x03", b"\x03\xff\x00", b"\x03\x04\xd1\x01", b"\x03\x01\xd1"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_ndef_text(raw)

    def test_utf16_is_explicitly_rejected(self):
        raw = bytearray(create_ndef_text_payload("hello"))
        raw[6] |= 0x80
        with self.assertRaisesRegex(ValueError, "UTF-16"):
            parse_ndef_text(raw)


class TagTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.dict(sys.modules, {"utime": FakeClock})
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_write_and_read(self):
        nfc = make_nfc()
        self.assertTrue(nfc.write_ndef_text("hello"))
        self.assertEqual(nfc.read_ndef_text(dump=False), "hello")
        self.assertEqual(nfc.reader.writes[0], 4)
        self.assertEqual(nfc.reader.writes[-1], 4)
        self.assertTrue(all(4 <= page < 40 for page in nfc.reader.writes))

    def test_full_capacity_and_replacement(self):
        nfc = make_nfc()
        # 144 bytes includes the TLV, record header, language, and terminator.
        nfc.write_ndef_text("x" * 134)
        self.assertEqual(nfc.read_ndef_text(dump=False), "x" * 134)
        nfc.write_ndef_text("")
        self.assertEqual(nfc.read_ndef_text(dump=False), "")

    def test_non_multiple_of_four_page_capacity(self):
        nfc = make_nfc(40)
        nfc.write_ndef_text("x" * 30)
        self.assertEqual(nfc.read_ndef_text(dump=False), "x" * 30)

    def test_too_large_does_not_write(self):
        nfc = make_nfc()
        with self.assertRaises(ValueError):
            nfc.write_ndef_text("x" * 135)
        self.assertEqual(nfc.reader.writes, [])

    def test_read_only_does_not_write(self):
        nfc = make_nfc()
        nfc.reader.memory[15] = 0x0F
        with self.assertRaises(ValueError):
            nfc.write_ndef_text("hello")
        self.assertEqual(nfc.reader.writes, [])

    def test_invalid_capability_container(self):
        nfc = make_nfc()
        nfc.reader.memory[12] = 0
        with self.assertRaises(ValueError):
            nfc.read_ndef_text(dump=False)

    def test_nak_is_failure(self):
        nfc = make_nfc()
        nfc.reader.ack = 0
        with self.assertRaisesRegex(OSError, "acknowledge"):
            nfc.write_ndef_text("hello")

    def test_readback_mismatch_is_failure(self):
        nfc = make_nfc()
        nfc.reader.corrupt_readback = True
        with self.assertRaisesRegex(OSError, "verification failed"):
            nfc.write_ndef_text("hello")

    def test_reserved_pages_are_rejected(self):
        nfc = make_nfc()
        with self.assertRaises(ValueError):
            nfc.write_ntag_page(3, b"test")
        self.assertEqual(nfc.reader.writes, [])


class MenuTests(unittest.TestCase):
    def test_read_then_write(self):
        with patch.object(tag_manager, "NFCReader") as factory:
            nfc = factory.return_value
            nfc.read_ndef_text.return_value = "stored text"
            with patch("builtins.input", side_effect=["r", "w", "new text", "q"]):
                with patch("builtins.print"):
                    tag_manager.main()
            self.assertEqual(nfc.wait_for_tag.call_count, 2)
            nfc.read_ndef_text.assert_called_once_with()
            nfc.write_ndef_text.assert_called_once_with("new text")
            nfc.close.assert_called_once_with()

    def test_failure_is_reported_and_menu_continues(self):
        with patch.object(tag_manager, "NFCReader") as factory:
            nfc = factory.return_value
            error = OSError("tag removed")
            nfc.write_ndef_text.side_effect = error
            with patch("builtins.input", side_effect=["w", "hello", "q"]):
                with patch("builtins.print") as output:
                    tag_manager.main()
            output.assert_any_call("Operation failed:", error)
            nfc.feedback.assert_called_once_with(False)
            nfc.close.assert_called_once_with()

    def test_interrupt_closes_hardware(self):
        with patch.object(tag_manager, "NFCReader") as factory:
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                with patch("builtins.print"):
                    tag_manager.main()
            factory.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
