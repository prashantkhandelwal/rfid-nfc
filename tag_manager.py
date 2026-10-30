"""Run on the Pico through a MicroPython serial console.

Upload nfc_combined.py, this file, a genuine mfrc522.py driver, and ssd1306.py.
The existing local mfrc522.py is application code, not the required driver.
Run `import tag_manager; tag_manager.main()` or execute this file directly.
Wiring: RC522 SPI0 SCK=6 MISO=4 MOSI=7 CS=5 RST=22;
OLED I2C0 SCL=13 SDA=12; buzzer=15.

Each menu selection handles one tag. Read reports UID validation, memory,
and NDEF text. Write asks for replacement text and verifies it after writing.
UID validation is informational, not access control; writing replaces the
existing NDEF message, including any non-text records. Only NFC Type 2 tags
with a readable capability container and UTF-8 text are supported for data I/O.
"""

from nfc_combined import NFCReader


def main():
    nfc = NFCReader()
    try:
        while True:
            print("\n[r] Read tag  [w] Write text  [q] Quit")
            choice = input("Choose: ").strip().lower()
            if choice == "q":
                break
            if choice not in ("r", "w"):
                print("Choose r, w, or q.")
                continue
            text = input("Replacement text: ") if choice == "w" else None
            print("Bring one tag closer...")
            try:
                nfc.wait_for_tag()
                if choice == "w":
                    nfc.write_ndef_text(text)
                    print("Write completed and verified.")
                    nfc.show("Write verified", text)
                    nfc.feedback(True)
                else:
                    result = nfc.read_ndef_text()
                    if result is None:
                        print("No NDEF Text record found.")
                        nfc.show("Read complete", "No text record")
                    else:
                        print("Text:", result)
                        nfc.show("Read complete", result)
            except (OSError, ValueError) as error:
                print("Operation failed:", error)
                nfc.show("Operation failed", str(error))
                nfc.feedback(False)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        nfc.close()


if __name__ == "__main__":
    main()
