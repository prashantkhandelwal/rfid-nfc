from mfrc522 import MFRC522
import utime

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
NTAG_READ = 0x30

def read_ntag_page(reader, page_num):
    """
    Sends NTAG READ command with proper CRC generation 
    and Crypto1 explicitly disabled.
    """
    # 1. Stop Crypto1 ciphering if left active from tag selection
    try:
        reader.stop_crypto1()
    except Exception:
        pass

    # 2. Prepare NTAG READ command [0x30, page_num]
    cmd = [NTAG_READ, page_num]

    # 3. Calculate 2-byte CRC using your library's built-in `_crc()` method
    crc_bytes = reader._crc(cmd)
    if crc_bytes:
        cmd.extend(crc_bytes)

    # 4. Clear bit framing to ensure 8-bit alignment (0x0D is BitFramingReg)
    try:
        reader._cflags(0x0D, 0x07)
    except Exception:
        pass

    # 5. Send frame via _tocard
    status, data, bits = reader._tocard(PCCD_TRANSCEIVE, cmd)
    return status, data

def parse_ndef_text(raw_bytes):
    """Extracts UTF-8 text from NDEF payload."""
    for i in range(len(raw_bytes) - 4):
        # 0x54 = Text Record Type ('T')
        if raw_bytes[i] == 0x54:
            status_byte = raw_bytes[i + 1]
            lang_len = status_byte & 0x3F
            start_idx = i + 2 + lang_len
            
            text_bytes = []
            for idx in range(start_idx, len(raw_bytes)):
                if raw_bytes[idx] == 0xFE:  # NDEF Terminator TLV
                    break
                text_bytes.append(raw_bytes[idx])
            
            try:
                return bytes(text_bytes).decode("utf-8")
            except Exception as e:
                return f"[Decode Error: {e}]"
    return None

print("Scanning for NTAG/Ultralight tag...")

while True:
    reader.init()
    stat, tag_type = reader.request(reader.REQIDL)
    
    if stat == reader.OK:
        stat, uid = reader.SelectTagSN()
        if stat == reader.OK:
            uid_hex = ":".join(["{:02X}".format(x) for x in uid])
            print("\n----------------------------------------")
            print("Tag Detected!")
            print("UID:", uid_hex)
            
            # Read Page 4
            status, data = read_ntag_page(reader, 4)
            print("Status:", status)
            print("Data:  ", data)
            
            if status == reader.OK and data:
                print("SUCCESS! Page 4 Data:", [hex(x) for x in data[:4]])
                
                # Dump NTAG Memory (Pages 4 through 44)
                print("\n--- Dumping NTAG Memory ---")
                dumped_bytes = []
                for p in range(4, 45):
                    st, d = read_ntag_page(reader, p)
                    if st == reader.OK and len(d) >= 4:
                        page_4bytes = d[:4]
                        dumped_bytes.extend(page_4bytes)
                        hex_str = " ".join("{:02X}".format(x) for x in page_4bytes)
                        print("Page {:02d}: {}".format(p, hex_str))
                    else:
                        print("Page {:02d}: Read failed (Status {})".format(p, st))
                        break
                
                # Extract Text Payload
                print("\n--- Decoded NDEF Text ---")
                text = parse_ndef_text(dumped_bytes)
                if text:
                    print("Text:", text)
                else:
                    print("No standard NDEF Text record found.")
            else:
                print("Read failed with status:", status)
                
            print("----------------------------------------")
            utime.sleep(3)
    utime.sleep(0.1)
