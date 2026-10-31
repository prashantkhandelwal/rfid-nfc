# rfid-nfc

MicroPython scripts for reading RFID tag IDs and reading/writing NFC NDEF text
with a Raspberry Pi Pico and an MFRC522 (RC522) reader. The interactive tag
manager includes SSD1306 OLED status messages and buzzer feedback.

## Features

- Display tag UIDs and decimal card IDs, with feedback for an editable allowlist.
- Read NFC Type 2 tag memory and decode the first UTF-8 NDEF Text record.
- Write replacement text within the tag's advertised capacity and verify it by
  reading back the written bytes.
- Choose one read or write operation at a time from a serial-console menu.

## Hardware and wiring

You will need a Raspberry Pi Pico running MicroPython, an RC522 reader,
compatible tags, a 128x32 SSD1306 I2C OLED, a PWM-compatible buzzer, and jumper
wires. The OLED and buzzer are required by the interactive tag manager.

The scripts use the following Pico **GPIO numbers**, not physical pin numbers:

| Component | Signal | Pico GPIO |
| --- | --- | --- |
| RC522 (SPI0) | SCK | GP6 |
| RC522 (SPI0) | MISO | GP4 |
| RC522 (SPI0) | MOSI | GP7 |
| RC522 (SPI0) | SDA / SS / CS | GP5 |
| RC522 (SPI0) | RST | GP22 |
| OLED (I2C0) | SCL | GP13 |
| OLED (I2C0) | SDA | GP12 |
| Buzzer | Signal | GP15 |

Use 3.3 V power and compatible 3.3 V logic, and connect component grounds to
Pico GND. The RC522 pin labeled `SDA` is chip select in this SPI configuration,
not an I2C data connection.

## Setup

1. Install MicroPython firmware for your Pico.
2. Connect the components as shown above.
3. Open a MicroPython serial console, for example through Thonny.
4. Upload these files to the Pico's filesystem:
   - [nfc_combined.py](nfc_combined.py)
   - [tag_manager.py](tag_manager.py)
   - A genuine MicroPython `mfrc522.py` driver exposing `MFRC522` with the
     `spi_id`, `sck`, `miso`, `mosi`, `cs`, and `rst` constructor arguments.
     It must provide `init`, `request`, `SelectTagSN`, `_cflags`, `_crc`,
     `_tocard`, `OK`, and `REQIDL`.
   - An `ssd1306.py` driver providing `SSD1306_I2C`.

**Important:** The repository's [mfrc522.py](mfrc522.py) is a legacy application
script, **not** the reader driver. Do not upload it under that name in place of
the genuine driver: it imports `MFRC522` from `mfrc522` itself and cannot supply
the required class. Neither hardware driver is bundled here.

## Usage

Run [tag_manager.py](tag_manager.py) directly on the Pico, or enter this in its
MicroPython REPL:

```python
import tag_manager
tag_manager.main()
```

The console presents:

```text
[r] Read tag  [w] Write text  [q] Quit
Choose:
```

- **Read (`r`):** Bring a tag close to the reader. The console reports its UID,
  decimal card ID, allowlist result, data-page dump, and decoded text, if present.
- **Write (`w`):** Enter replacement text, then bring a tag close and keep it
  there until the write and read-back verification finish.
- **Quit (`q`):** Exit the menu and release the buzzer. Ctrl+C also stops it.

Edit `VALID_CARDS` in [nfc_combined.py](nfc_combined.py) to change the allowlist.
Use the decimal `CARD ID` printed during a scan, not the hexadecimal UID.
Allowlist validation is informational: an invalid card ID does **not** prevent
reading or writing.

### Supported tags and limitations

- Data I/O requires an NFC Type 2 tag with a supported, readable capability
  container, such as a suitably formatted NTAG tag. UID detection alone does not
  mean a tag supports these read/write operations.
- The writer requires unrestricted write access and writes data starting at
  page 4. It does not format tags or unlock protected pages.
- Writing replaces the existing NDEF message, including non-text records. Use a
  spare tag or back up important contents before writing.
- Text is UTF-8. UTF-16 and chunked NDEF records are not supported.
- The writer creates one short NDEF Text record. With the default `en` language
  code, its encoding limit is 247 UTF-8 text bytes; the tag's capacity may impose
  a lower limit. A 144-byte data area fits at most 134 text bytes. These limits
  count bytes, not characters.
- Keep the tag in place throughout an operation. Interrupted writes can leave
  an empty or incomplete message; failures are reported in the console and OLED.

## Repository files

| File | Purpose |
| --- | --- |
| [tag_manager.py](tag_manager.py) | Interactive read/write entry point. |
| [nfc_combined.py](nfc_combined.py) | Reader abstraction, feedback, NDEF parsing, and verified writes. |
| [nfc_read.py](nfc_read.py) | Original standalone reader with a fixed page 4-44 dump. |
| [nfc_write.py](nfc_write.py) | Original standalone writer using `TEXT_TO_STORE`; writes repeatedly while scanning. |
| [mfrc522.py](mfrc522.py) | Legacy UID-validation application with OLED icons and buzzer feedback, not a driver. |
| [test_nfc_combined.py](test_nfc_combined.py) | Host-side unit tests using simulated hardware. |

Prefer the interactive tag manager for capacity checks and read-back verification
rather than the original standalone scripts.

## Tests

From the repository directory on a computer with Python installed:

```sh
python -m unittest test_nfc_combined.py
```

The tests use the Python standard library and do not require a Pico or hardware
drivers. They cover NDEF encoding/parsing, capacity and access checks, write
acknowledgments, read-back verification, and menu behavior. Physical hardware
operation must be checked separately on the Pico.

## License

[MIT](LICENSE).
