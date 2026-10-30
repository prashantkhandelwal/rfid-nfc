from mfrc522 import MFRC522
import utime
from machine import Pin, PWM, I2C
from ssd1306 import SSD1306_I2C
import framebuf

WIDTH  = 128 
HEIGHT = 32

SCL = 13
SDA = 12

i2c = I2C(0, scl=Pin(SCL), sda=Pin(SDA), freq=200000)
display = SSD1306_I2C(WIDTH, HEIGHT, i2c)

buzzer = PWM(Pin(15))
reader = MFRC522(spi_id=0, sck=6, miso=4, mosi=7, cs=5, rst=22)

print("Bring TAG closer...\n")

valid_cards = ['108333494', '105576231']  # list of valid card IDs

# --- Icon setup ---
icon_error_bytes = bytes.fromhex(
    "00000001ff8003ffc00700e00e00701c003838001c70000e60c30660e706607e06603c06603c06607e0660e70660c30670000e38001e1c003c0e00780700f003ffe001ffc0000000"
)

icon_success_bytes = bytes.fromhex(
    "0000000000000000000000000000000000180000380000700000e00001c00003801807001c0e000e1c0007380003f00001e00000c000000000000000000000000000000000000000"
)

icon_startup_bytes = bytes.fromhex(
    "0000000000000000000000000c00301c003838001c3b81dc7381ce773cee677ee6666666666e66777eee773cee7381ce3b81dc38001c1c00380c0030000000000000000000000000"
)

# 32x16 pixels (64 bytes = 512 bits)
ICON_WIDTH = 24
ICON_HEIGHT = 24

icon_error_fb = framebuf.FrameBuffer(bytearray(icon_error_bytes), ICON_WIDTH, ICON_HEIGHT, framebuf.MONO_HLSB)
icon_success_fb = framebuf.FrameBuffer(bytearray(icon_success_bytes), ICON_WIDTH, ICON_HEIGHT, framebuf.MONO_HLSB)
icon_startup_fb = framebuf.FrameBuffer(bytearray(icon_startup_bytes), ICON_WIDTH, ICON_HEIGHT, framebuf.MONO_HLSB)

def display_startup():
    display.fill(0)
    display.blit(icon_startup_fb, 0, 8)
    display.text("Scan Tag", 32, 16)
    display.show()

def display_oled(text, isValid):
    display.fill(0)
    if isValid:
        display.blit(icon_success_fb, 0, 8)
        display.text("Success ", 40, 8)
        display.text(str(text), 30, 20)
    else:
        display.blit(icon_error_fb, 0, 8)
        display.text("Invalid", 40, 8)
        display.text(str(text), 30, 20)
    display.show()

def play_tone(frequency, duration):
    buzzer.freq(frequency)
    buzzer.duty_u16(32768)   # 50% duty cycle
    utime.sleep_ms(duration)
    buzzer.duty_u16(0)
    utime.sleep_ms(100)      # short pause

def buzz_valid():
    play_tone(2000, 150)

def buzz_invalid():
    play_tone(2000, 100)
    utime.sleep_ms(50)
    play_tone(2000, 100)

# Track last detection time
last_detection = 0
cooldown_ms = 2000  # 2 seconds

display_startup()

while True:
    current_time = utime.ticks_ms()
    if utime.ticks_diff(current_time, last_detection) >= cooldown_ms:
        reader.init()
        (stat, tag_type) = reader.request(reader.REQIDL)
        if stat == reader.OK:
            (stat, uid) = reader.SelectTagSN()
            if stat == reader.OK:
                card = int.from_bytes(bytes(uid), "little", False)
                print("CARD ID:", card)

                if str(card) in valid_cards:
                    display_oled(card, True)
                    print("Valid card detected")
                    buzz_valid()
                    utime.sleep_ms(2500)
                    display_startup()
                else:
                    display_oled(card, False)
                    print("Invalid card detected")
                    buzz_invalid()
                    utime.sleep_ms(2500)
                    display_startup()

                last_detection = utime.ticks_ms()

    utime.sleep_ms(200)

