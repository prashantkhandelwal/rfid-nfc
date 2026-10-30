from mfrc522 import MFRC522
import utime

# Initialize MFRC522 reader
reader = MFRC522(
    spi_id=0,
    sck=6,
    miso=4,
    mosi=7,
    cs=5,
    rst=22
)

# Constants
PCCD_TRANSCEIVE = 0x0C
NTAG_WRITE = 0xA2


def write_ntag_page(reader, page_num, data_4bytes):
    """
    Writes a 4-byte block to a specific NTAG page.
    """
    if len(data_4bytes) != 4:
        raise ValueError("Data must be exactly 4 bytes long.")

    # Disable Crypto1 if left active
    try:
        reader.stop_crypto1()
    except Exception:
        pass

    # Construct WRITE command: [0xA2, page, byte0, byte1, byte2, byte3]
    cmd = [NTAG_WRITE, page_num] + list(data_4bytes)

    # Append 2-byte CRC calculated by internal coprocessor
    crc_bytes = reader._crc(cmd)
    if crc_bytes:
        cmd.extend(crc_bytes)

    # Clear partial bit framing to 8-bit alignment
    try:
        reader._cflags(0x0D, 0x07)
    except Exception:
        pass

    # Send frame via _tocard
    status, data, bits = reader._tocard(PCCD_TRANSCEIVE, cmd)
    return status


def create_ndef_text_payload(text_string, lang="en"):
    """
    Builds a formatted NDEF Text Record byte array.
    """
    text_bytes = text_string.encode("utf-8")
    lang_bytes = lang.encode("ascii")

    # Status byte: Bit 7 = 0 (UTF-8), Bits 5..0 = language code length
    status_byte = len(lang_bytes) & 0x3F

    # Inner NDEF Record Payload
    record_payload = [status_byte] + list(lang_bytes) + list(text_bytes)

    # Record Header: [0xD1 (MB/ME/SR/TNF=1), 0x01 (Type Length), Payload Length, 0x54 ('T')]
    ndef_record = [0xD1, 0x01, len(record_payload), 0x54] + record_payload

    # Wrap in NDEF Message TLV (0x03) and terminate with (0xFE)
    ndef_message = [0x03, len(ndef_record)] + ndef_record + [0xFE]

    return ndef_message


def write_ndef_text(reader, text_to_write):
    """
    Pads NDEF payload to 4-byte boundaries and writes sequentially from Page 4.
    """
    payload = create_ndef_text_payload(text_to_write)

    # Pad payload with 0x00 bytes to fill complete 4-byte pages
    while len(payload) % 4 != 0:
        payload.append(0x00)

    total_pages = len(payload) // 4
    start_page = 4

    print(
        f"Writing '{text_to_write}' ({len(payload)} bytes across {total_pages} pages)..."
    )

    for i in range(total_pages):
        current_page = start_page + i
        page_data = payload[i * 4 : (i + 1) * 4]

        status = write_ntag_page(reader, current_page, page_data)
        hex_str = " ".join("{:02X}".format(x) for x in page_data)

        if status == reader.OK:
            print(f"Page {current_page:02d} written successfully: {hex_str}")
        else:
            print(
                f"Failed writing to Page {current_page:02d} (Status: {status})"
            )
            return False

        # Short pause between page write cycles
        utime.sleep_ms(10)

    return True


# Main loop
print("Scanning for NTAG to write...")

TEXT_TO_STORE = "Hello from Raspberry Pi Pico!"

while True:
    reader.init()
    stat, tag_type = reader.request(reader.REQIDL)

    if stat == reader.OK:
        stat, uid = reader.SelectTagSN()
        if stat == reader.OK:
            uid_hex = ":".join(["{:02X}".format(x) for x in uid])
            print("\n----------------------------------------")
            print("Tag Detected! UID:", uid_hex)

            # Perform write starting at Page 4
            success = write_ndef_text(reader, TEXT_TO_STORE)

            if success:
                print("\nWrite completed! Tag can now be scanned by smartphones.")
            else:
                print("\nWrite operation encountered errors.")

            print("----------------------------------------")
            utime.sleep(5)
    utime.sleep(0.1)