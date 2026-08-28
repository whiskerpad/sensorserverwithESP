"""
I2C 20x4 キャラクター LCD 診断スクリプト

目的: 実機で表示できる文字を全部確認する
  - I2C アドレス自動検出 (0x27, 0x3F を試す)
  - 全キャラコードを 5 秒ローテで表示 (ASCII、半角カナ、記号、サンプル文)

依存: RPLCD, smbus2

前提: I2C 有効化済み (sudo raspi-config → Interface Options → I2C → Enable)

配線 (I2C バックパック付き 20x4 LCD):
  LCD VCC  →  Pi Pin 2  (5V)      ※ 5V モジュールが標準、3.3V 版もあるので実物確認
  LCD GND  →  Pi Pin 6  (GND)
  LCD SDA  →  Pi Pin 3  (GPIO2, SDA)
  LCD SCL  →  Pi Pin 5  (GPIO3, SCL)

使い方:
  python3 i2c_lcd_charmap_test.py
  → 5 秒ごとにページが切替わり、全キャラコードを順に表示
  → Ctrl+C で停止
"""

import time
import sys
from RPLCD.i2c import CharLCD

# ============================================================
#  設定
# ============================================================
LCD_COLS = 20
LCD_ROWS = 4
I2C_ADDRS_TO_TRY = [0x27, 0x3F, 0x38, 0x20]  # PCF8574 のよくあるアドレス
I2C_PORT = 1                                    # Pi 4B は I2C1
PAGE_INTERVAL = 5                               # 秒 (ページ切替間隔)


def detect_lcd():
    """接続できる I2C アドレスを見つけて CharLCD を返す"""
    for addr in I2C_ADDRS_TO_TRY:
        try:
            print(f"Trying I2C address 0x{addr:02X}...")
            lcd = CharLCD(
                i2c_expander='PCF8574',
                address=addr,
                port=I2C_PORT,
                cols=LCD_COLS,
                rows=LCD_ROWS,
                dotsize=8,
                charmap='A02',     # 'A00'=Japanese Katakana, 'A02'=European
                auto_linebreaks=True,
                backlight_enabled=True
            )
            lcd.clear()
            lcd.write_string("LCD detected!")
            lcd.crlf()
            lcd.write_string(f"I2C addr: 0x{addr:02X}")
            time.sleep(1)
            print(f"  → SUCCESS at 0x{addr:02X}")
            return lcd, addr
        except Exception as e:
            print(f"  → failed: {e}")
    return None, None


def show_page(lcd, title, chars, cols=LCD_COLS, rows=LCD_ROWS):
    """1 ページを表示 (title を 1 行目、chars を 2-4 行目に埋める)"""
    lcd.clear()
    lcd.cursor_pos = (0, 0)
    lcd.write_string(title[:cols])

    # chars を rows-1 行に流し込み
    for row in range(1, rows):
        start = (row - 1) * cols
        chunk = chars[start:start + cols]
        if not chunk:
            break
        lcd.cursor_pos = (row, 0)
        # 直接バイトを書く必要がある文字コードは write に bytes で送る
        try:
            lcd.write_string(chunk)
        except Exception:
            # 変換できない文字は? に置換
            safe = ''.join(c if ord(c) < 0x100 else '?' for c in chunk)
            lcd.write_string(safe)


def show_raw_bytes_page(lcd, title, start_code, count, cols=LCD_COLS, rows=LCD_ROWS):
    """
    キャラコードを直接書く (0x80 以上の半角カナ等を確認するため)。
    RPLCD.write() は int または bytes を受け付ける。
    """
    lcd.clear()
    lcd.cursor_pos = (0, 0)
    lcd.write_string(title[:cols])

    code = start_code
    for row in range(1, rows):
        lcd.cursor_pos = (row, 0)
        for col in range(cols):
            if code >= start_code + count:
                lcd.write_string(' ')
            else:
                try:
                    lcd.write(code)
                except Exception:
                    lcd.write_string('?')
            code += 1


def main():
    lcd, addr = detect_lcd()
    if not lcd:
        print("\nERROR: No LCD found. Check:")
        print("  1. I2C enabled? sudo raspi-config → Interface Options → I2C")
        print("  2. Wiring: SDA=Pin3, SCL=Pin5, VCC=Pin2(5V), GND=Pin6")
        print("  3. Address: sudo i2cdetect -y 1")
        sys.exit(1)

    time.sleep(2)

    # ページ定義: (タイトル, レンダー関数)
    pages = [
        # 1. 情報ページ
        lambda: show_page(lcd,
            "I2C LCD DIAGNOSTIC",
            f"Cols: {LCD_COLS} Rows: {LCD_ROWS} Addr: 0x{addr:02X}  Rotate: {PAGE_INTERVAL}s"[:60]
        ),

        # 2. ASCII 0x20-0x6F (' ' 〜 'o') 3 行 × 20 = 60 文字
        lambda: show_raw_bytes_page(lcd, "ASCII 0x20-0x6F", 0x20, 60),

        # 3. ASCII 0x70-0x7E ('p' 〜 '~') + 空
        lambda: show_raw_bytes_page(lcd, "ASCII 0x70-0x7F", 0x70, 16),

        # 4. 0x80-0x9F (charmap 'A02' なら European、'A00' なら空 or 記号)
        lambda: show_raw_bytes_page(lcd, "0x80-0x9F range", 0x80, 32),

        # 5. 0xA0-0xDF (charmap 'A00' なら半角カナ、'A02' なら記号)
        lambda: show_raw_bytes_page(lcd, "0xA0-0xDF (Katakana?)", 0xA0, 64),

        # 6. 0xE0-0xFF (記号・数式)
        lambda: show_raw_bytes_page(lcd, "0xE0-0xFF (Symbols)", 0xE0, 32),

        # 7. サンプル: 温度表示レイアウトの模擬
        lambda: show_page(lcd,
            "Sample display",
            "ESP-A1B2  25.3C -55" + " ".ljust(1) +
            "NOW-F734  29.4C -30" + " ".ljust(1) +
            "2026/08/02 16:30:45 ",
            cols=LCD_COLS, rows=LCD_ROWS
        ),

        # 8. サンプル: 半角カナで書けそうな文字列 (charmap='A00' 用)
        lambda: show_page(lcd,
            "KANA test",
            # 0xC3=ﾆ, 0xB6=ｶ, 0xBE=ｾ 等を混ぜて確認 (charmap='A00' の場合のみ表示可)
            "See char codes  " +
            "if you can read  " +
            "katakana        "
        ),
    ]

    print(f"\nStarting rotation. Page interval: {PAGE_INTERVAL}s. Ctrl+C to stop.\n")

    try:
        page_num = 0
        while True:
            print(f"[Page {page_num % len(pages) + 1}/{len(pages)}]")
            pages[page_num % len(pages)]()
            page_num += 1
            time.sleep(PAGE_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        lcd.clear()
        lcd.write_string("Test finished.")
        time.sleep(1)
        lcd.close(clear=True)


if __name__ == '__main__':
    main()
