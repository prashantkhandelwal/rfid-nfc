"""MicroPython RFID validation, OLED/buzzer feedback, and NTAG text I/O.

Requires a real mfrc522 driver exposing MFRC522, plus ssd1306 on the Pico.
See tag_manager.py for interactive use. Original scripts are unchanged.
"""

VALID_CARDS = ("108333494", "105576231")
FIRST_DATA_PAGE = 4
TRANSCEIVE = 0x0C


def create_ndef_text_payload(text, lang="en"):
    """Encode a single UTF-8 text record using a short NDEF TLV."""
    language = lang.encode("ascii")
    if not 1 <= len(language) <= 63:
        raise ValueError("Language code must contain 1 to 63 ASCII bytes.")
    body = bytes([len(language)]) + language + text.encode("utf-8")
    if len(body) + 4 > 254:
        raise ValueError("Text is too long for a short NDEF TLV.")
    record = bytes([0xD1, 1, len(body), 0x54]) + body
    return bytes([0x03, len(record)]) + record + b"\xfe"


def parse_ndef_text(raw_bytes):
    """Read the first UTF-8 Text record, respecting TLV and record lengths."""
    raw = bytes(raw_bytes)
    position = 0
    while position < len(raw):
        kind = raw[position]
        position += 1
        if kind == 0xFE:
            return None
        if kind == 0:
            continue
        if position >= len(raw):
            raise ValueError("Missing TLV length.")
        length = raw[position]
        position += 1
        if length == 0xFF:
            if position + 2 > len(raw):
                raise ValueError("Truncated extended TLV length.")
            length = (raw[position] << 8) | raw[position + 1]
            position += 2
        end = position + length
        if end > len(raw):
            raise ValueError("TLV exceeds available tag data.")
        if kind != 0x03:
            position = end
            continue
        message = raw[position:end]
        offset = 0
        while offset < len(message):
            if offset + 2 > len(message):
                raise ValueError("Truncated NDEF header.")
            header, type_length = message[offset:offset + 2]
            offset += 2
            if header & 0x20:
                raise ValueError("Chunked NDEF records are not supported.")
            length_bytes = 1 if header & 0x10 else 4
            if offset + length_bytes > len(message):
                raise ValueError("Truncated NDEF payload length.")
            payload_length = 0
            for value in message[offset:offset + length_bytes]:
                payload_length = (payload_length << 8) | value
            offset += length_bytes
            id_length = 0
            if header & 0x08:
                if offset >= len(message):
                    raise ValueError("Missing NDEF ID length.")
                id_length = message[offset]
                offset += 1
            payload_start = offset + type_length + id_length
            record_end = payload_start + payload_length
            if record_end > len(message):
                raise ValueError("Truncated NDEF record.")
            record_type = message[offset:offset + type_length]
            payload = message[payload_start:record_end]
            if header & 0x07 == 1 and record_type == b"T":
                if not payload:
                    raise ValueError("Missing Text record status byte.")
                if payload[0] & 0x80:
                    raise ValueError("UTF-16 Text records are not supported.")
                text_start = 1 + (payload[0] & 0x3F)
                if text_start > len(payload):
                    raise ValueError("Truncated Text record language code.")
                return payload[text_start:].decode("utf-8")
            offset = record_end
        return None
    return None


class NFCReader:
    """Use the original Pico wiring; initialize hardware only on construction."""

    def __init__(self, valid_cards=VALID_CARDS):
        from machine import Pin, PWM, I2C
        from mfrc522 import MFRC522
        from ssd1306 import SSD1306_I2C

        self.reader = MFRC522(
            spi_id=0, sck=6, miso=4, mosi=7, cs=5, rst=22
        )
        self.display = SSD1306_I2C(
            128, 32, I2C(0, scl=Pin(13), sda=Pin(12), freq=200000)
        )
        self.buzzer = PWM(Pin(15))
        self.buzzer.duty_u16(0)
        self.valid_cards = tuple(str(card) for card in valid_cards)
        self.show("Ready", "Scan tag")

    def show(self, title, detail="", extra=""):
        self.display.fill(0)
        for line, text in enumerate((title, detail, extra)):
            self.display.text(str(text)[:16], 0, line * 10)
        self.display.show()

    def feedback(self, success):
        import utime

        for _ in range(1 if success else 2):
            self.buzzer.freq(2000)
            self.buzzer.duty_u16(32768)
            try:
                utime.sleep_ms(150 if success else 100)
            finally:
                self.buzzer.duty_u16(0)
            utime.sleep_ms(100)

    def wait_for_tag(self):
        """Return UID, decimal card ID, and allowlist result for one scan."""
        import utime

        self.show("Scan tag")
        while True:
            self.reader.init()
            status, _ = self.reader.request(self.reader.REQIDL)
            if status == self.reader.OK:
                status, uid = self.reader.SelectTagSN()
                if status == self.reader.OK:
                    card = 0
                    for index, value in enumerate(uid):
                        card |= value << (8 * index)
                    card_id = str(card)
                    valid = card_id in self.valid_cards
                    print("UID:", ":".join("{:02X}".format(x) for x in uid))
                    print("CARD ID:", card_id)
                    print("Valid card" if valid else "Invalid card")
                    self.show("Valid card" if valid else "Invalid card", card_id)
                    self.feedback(valid)
                    return uid, card_id, valid
            utime.sleep_ms(200)

    def _command(self, command):
        # Clear Status2Reg.MFCrypto1On and align BitFramingReg to whole bytes.
        self.reader._cflags(0x08, 0x08)
        self.reader._cflags(0x0D, 0x07)
        crc = self.reader._crc(command)
        if crc is None or len(crc) != 2:
            raise OSError("MFRC522 failed to generate CRC.")
        status, data, bits = self.reader._tocard(
            TRANSCEIVE, list(command) + list(crc)
        )
        if status != self.reader.OK:
            raise OSError("Tag command failed (status {}).".format(status))
        return data, bits

    def read_ntag_page(self, page):
        """READ returns four pages (16 bytes), starting at the requested page."""
        if not 0 <= page <= 255:
            raise ValueError("Page must be between 0 and 255.")
        data, bits = self._command([0x30, page])
        if bits < 128 or len(data) < 16:
            raise OSError("Incomplete NTAG READ response.")
        return bytes(data[:16])

    def _capacity(self, writing=False):
        cc = self.read_ntag_page(3)[:4]
        if cc[0] != 0xE1 or cc[1] >> 4 != 1 or cc[2] < 2:
            raise ValueError("Tag has no supported NFC Type 2 capability container.")
        if cc[3] >> 4:
            raise ValueError("Tag does not allow unrestricted reading.")
        if writing and cc[3] & 0x0F:
            raise ValueError("Tag does not allow unrestricted writing.")
        capacity = cc[2] * 8
        if FIRST_DATA_PAGE + capacity // 4 > 256:
            raise ValueError("Tag capacity exceeds supported page addressing.")
        return capacity

    def read_ndef_text(self, dump=True):
        capacity = self._capacity()
        raw = bytearray()
        page_count = capacity // 4
        for offset in range(0, page_count, 4):
            # Keep all four pages of the final READ inside the data area.
            start = min(offset, page_count - 4)
            data = self.read_ntag_page(FIRST_DATA_PAGE + start)
            chunk = data[(offset - start) * 4:]
            raw.extend(chunk)
            if dump:
                for index in range(0, len(chunk), 4):
                    print("Page {:02d}: {}".format(
                        FIRST_DATA_PAGE + offset + index // 4,
                        " ".join("{:02X}".format(x) for x in chunk[index:index + 4])
                    ))
        return parse_ndef_text(raw)

    def write_ntag_page(self, page, data):
        if not FIRST_DATA_PAGE <= page <= 255:
            raise ValueError("Only data pages 4 through 255 may be written.")
        if len(data) != 4:
            raise ValueError("Data must be exactly four bytes.")
        response, bits = self._command([0xA2, page] + list(data))
        if bits != 4 or not response or response[0] & 0x0F != 0x0A:
            raise OSError("Tag did not acknowledge page {}.".format(page))

    def write_ndef_text(self, text):
        """Write within advertised data capacity, then verify every byte."""
        import utime

        payload = create_ndef_text_payload(text)
        payload += b"\x00" * (-len(payload) % 4)
        capacity = self._capacity(writing=True)
        if len(payload) > capacity:
            raise ValueError("Encoded text needs {} bytes; tag has {}.".format(
                len(payload), capacity
            ))
        # Invalidate the message until all subsequent pages have been written.
        self.write_ntag_page(FIRST_DATA_PAGE, b"\x03\x00\xfe\x00")
        utime.sleep_ms(10)
        for offset in range(4, len(payload), 4):
            self.write_ntag_page(FIRST_DATA_PAGE + offset // 4, payload[offset:offset + 4])
            utime.sleep_ms(10)
        self.write_ntag_page(FIRST_DATA_PAGE, payload[:4])
        utime.sleep_ms(10)
        for offset in range(0, len(payload), 4):
            page = FIRST_DATA_PAGE + offset // 4
            start = min(page, FIRST_DATA_PAGE + capacity // 4 - 4)
            data = self.read_ntag_page(start)
            index = (page - start) * 4
            if data[index:index + 4] != payload[offset:offset + 4]:
                raise OSError("Write verification failed at page {}.".format(page))
        return True

    def close(self):
        self.buzzer.duty_u16(0)
        self.buzzer.deinit()
