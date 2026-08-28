"""
I2C 20x4 LCD 温度モニタリング状態表示 (拡張版)

拡張機能 (2026-08-07):
  1. 半角カナ nickname 対応
     - Flask ダッシュボードで「レイキャクトウ1」等の全角カタカナを nickname 設定
     - LCD 表示時に jaconv で自動的に半角カナに変換して LCD に送出
     - 漢字は '.' 置換 (HD44780 の物理制約)
  2. RSSI バー アイコン (CGRAM slot 0-4)
     - 数値 -55 の代わりに WiFi 風の 5 段階バーで視覚化
  3. カメラ/AP/WLAN アイコン (CGRAM slot 5-7)
     - AP+/WAN+/CAM+ の "+" を専用アイコンに置換

レイアウト (20x4):
    Line 1: 2026/08/07  09:30:45   (日付+時刻、20 chars)
    Line 2: AP[a] WAN[w] CAM[c] p/n (icon 3 個 + ページ番号)
    Line 3: <名前 10chars>  25.3C [rssi_icon]
    Line 4: <名前 10chars>  29.4C [rssi_icon]
"""

import os
import sys
import time
import glob
import subprocess
import logging
from datetime import datetime

import requests
from RPLCD.i2c import CharLCD

try:
    import jaconv
    JACONV_AVAILABLE = True
except ImportError:
    JACONV_AVAILABLE = False


# ============================================================
#  設定 (環境変数でオーバーライド可)
# ============================================================
LCD_COLS         = int(os.getenv('LCD_COLS', '20'))
LCD_ROWS         = int(os.getenv('LCD_ROWS', '4'))
I2C_ADDR         = int(os.getenv('LCD_I2C_ADDR', '0x27'), 16)
I2C_PORT         = int(os.getenv('LCD_I2C_PORT', '1'))
FLASK_URL        = os.getenv('FLASK_URL', 'http://localhost:5000')
REFRESH_SEC      = float(os.getenv('LCD_REFRESH_SEC', '2'))
ROTATION_SEC     = float(os.getenv('LCD_ROTATE_SEC', '5'))
SENSORS_PER_PAGE = int(os.getenv('LCD_SENSORS_PER_PAGE', '2'))
# View 切替 (2026-08-09 追加): センサー行末尾を RSSI バー ↔ 経過時間 で交互表示
VIEW_TOGGLE_SEC  = float(os.getenv('LCD_VIEW_TOGGLE_SEC', '3'))


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger('i2c_lcd')


# ============================================================
#  CGRAM カスタム文字定義 (各 5x8 pixel、8 スロット = 全部使用)
# ============================================================

# Slot 0-4: RSSI バー (WiFi 風、左から積み上がる 4 本の縦棒)
#   Level 0 = 空、 Level 4 = 全て表示
#   各バーの高さ: col 0 = 2px, col 1 = 4px, col 2 = 6px, col 3 = 8px
def _make_rssi_icon(level):
    """RSSI バー アイコン生成 (level = 0-4)"""
    icon = [0] * 8  # 8 行、各行 5 bit
    heights = [2, 4, 6, 8]
    for col in range(min(level, 4)):
        h = heights[col]
        bit = 1 << (4 - col)  # HD44780 CGRAM: bit4 = 左端
        for row in range(8 - h, 8):
            icon[row] |= bit
    return icon

ICON_RSSI = [_make_rssi_icon(i) for i in range(5)]  # 5 個

# Slot 5: カメラアイコン (5x8、上=シャッターボタン、中央=レンズ、下=本体底面)
ICON_CAMERA = [
    0b00000,
    0b00110,   # シャッターボタン
    0b11111,   # カメラ本体天面
    0b10101,   # レンズ (上部)
    0b11011,   # レンズ (中心)
    0b10101,   # レンズ (下部)
    0b11111,   # カメラ本体底面
    0b00000,
]

# Slot 6: AP アイコン (上=電波、下=アンテナ本体)
ICON_AP = [
    0b11111,   # 電波波形 (上)
    0b01010,   # 電波
    0b00100,   # 電波波形 (下)
    0b00100,   # アンテナ先端
    0b01110,   # アンテナ本体
    0b00100,   # ポール
    0b00100,
    0b11111,   # 台座
]

# Slot 7: WLAN アイコン (地球儀、赤道 2 本入りでより地球らしい)
ICON_WLAN = [
    0b01110,   # 上輪郭
    0b10101,   # 北半球
    0b11111,   # 赤道
    0b10101,   # 南半球
    0b11111,
    0b10101,
    0b01110,   # 下輪郭
    0b00000,   # 余白
]


# ============================================================
#  半角カナ変換 (Python Unicode → LCD 送信可能バイト列)
# ============================================================

def nickname_to_lcd_bytes(nickname):
    """
    Nickname 文字列を LCD 送信可能なバイト列に変換する。

    処理:
      1. jaconv で全角カナ → 半角カナ変換 (全角数字・英字も半角化)
      2. 各文字を LCD バイト値にマッピング:
         - ASCII (U+0020-U+007E) → そのまま
         - 半角カナ (U+FF61-U+FF9F) → 0xA1-0xDF
         - その他 (漢字・記号) → '.' 置換
    """
    if not nickname:
        return []

    # jaconv がインストールされていれば全角→半角変換
    if JACONV_AVAILABLE:
        try:
            nickname = jaconv.z2h(nickname, kana=True, digit=True, ascii=True)
        except Exception:
            pass  # 変換失敗時はそのまま

    result = []
    for ch in nickname:
        code = ord(ch)
        if 0x20 <= code <= 0x7E:
            # ASCII: そのまま
            result.append(code)
        elif 0xFF61 <= code <= 0xFF9F:
            # 半角カナ: HD44780 の 0xA1-0xDF にマップ
            result.append(0xA1 + (code - 0xFF61))
        else:
            # 漢字等の非対応文字は '.' に置換
            result.append(ord('.'))
    return result


# ============================================================
#  経過時間 (age) ユーティリティ (2026-08-09 追加)
#    Flask /api/sensors の timestamp フィールドを datetime に戻し、
#    現在時刻との差を LCD 表示用 4 文字幅の文字列に整形する。
# ============================================================

def parse_timestamp(ts):
    """
    SQLite/Flask から返る timestamp を naive datetime に変換。
    受理形式:
      - "2026-08-07 09:30:45"   (SQLite CURRENT_TIMESTAMP、ローカル時刻運用前提)
      - "2026-08-07T09:30:45"   (ISO 8601 T セパレータ)
      - "2026-08-07T09:30:45.123456"
    パース失敗時は None (呼び出し側で '---' 表示)。
    """
    if not ts:
        return None
    if not isinstance(ts, str):
        return None
    s = ts.replace('T', ' ').split('.')[0]  # 小数秒とタイムゾーンは切捨て
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def format_age(seconds):
    """
    経過秒数を 4 文字幅の LCD 表示文字列に整形。
      None/負    → " ---"    (データなし/クロックずれ)
      < 60s      → " now"
      1-59m      → " 12m"    (分単位、右寄せ)
      1h-9.9h    → "1.5h"    (小数 1 桁の時間)
      10h-23h    → "10h "    (整数時間 + 空白)
      >= 24h     → " >1d"    (24h 超えは 1 日以上として集約)
    """
    if seconds is None:
        return ' ---'
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return ' ---'
    if s < 0:
        return ' ---'
    if s < 60:
        return ' now'
    if s < 3600:
        return f'{s // 60:3d}m'      # " 12m"
    if s < 10 * 3600:
        # 小数 1 桁時間: "1.5h"。境界 (例 35999s → 9.9997h → round 10.0h) で
        # 5 文字化しないようにガード。
        h_disp = round(s / 3600, 1)
        if h_disp >= 10.0:
            return '10h '
        return f'{h_disp:.1f}h'      # "1.5h" (4 chars)
    if s < 24 * 3600:
        return f'{s // 3600:2d}h '   # "10h " (4 chars、末尾スペース)
    return ' >1d'


class LCDDisplay:
    def __init__(self, addr=I2C_ADDR):
        self.lcd = CharLCD(
            i2c_expander='PCF8574',
            address=addr,
            port=I2C_PORT,
            cols=LCD_COLS,
            rows=LCD_ROWS,
            dotsize=8,
            charmap='A02',
            auto_linebreaks=False,
            backlight_enabled=True,
        )

        # CGRAM に 8 個のカスタム文字を登録
        # RPLCD の create_char(location, [row0, row1, ..., row7])
        for i, bitmap in enumerate(ICON_RSSI):
            self.lcd.create_char(i, bitmap)          # slot 0-4
        self.lcd.create_char(5, ICON_CAMERA)         # slot 5
        self.lcd.create_char(6, ICON_AP)             # slot 6
        self.lcd.create_char(7, ICON_WLAN)           # slot 7

        # カーソルを CGRAM から DDRAM に戻すため空セルを書く必要あり
        # (create_char は内部で CGRAM アドレスをセットするため)
        self.lcd.cursor_pos = (0, 0)

        self.rotation_page = 0
        # view_mode = 'rssi' or 'age' (2026-08-09 追加、末尾を交互表示)
        self.view_mode = 'rssi'
        logger.info(f"LCD initialized at 0x{addr:02X}, {LCD_COLS}x{LCD_ROWS}")
        logger.info(f"CGRAM: 5 RSSI bars + camera + AP + WLAN icons")
        logger.info(f"jaconv available: {JACONV_AVAILABLE}")

    # ------------------- 情報取得 -------------------

    def get_status(self):
        info = {
            'flask_alive': False,
            'ap_running': False,
            'wlan0_ok': self._check_wlan0(),
            'camera_present': self._check_camera(),
            'sensors': [],
        }
        try:
            r = requests.get(f'{FLASK_URL}/api/status/ap', timeout=1)
            info['ap_running'] = bool(r.json().get('ap_running', False))
            info['flask_alive'] = True
        except Exception as e:
            logger.debug(f"AP status fetch failed: {e}")

        try:
            r = requests.get(f'{FLASK_URL}/api/sensors', timeout=2)
            info['sensors'] = r.json().get('sensors', [])
        except Exception as e:
            logger.debug(f"Sensors fetch failed: {e}")

        return info

    def _check_wlan0(self):
        try:
            r = subprocess.run(
                ['ip', '-4', 'addr', 'show', 'wlan0'],
                capture_output=True, text=True, timeout=1
            )
            return 'inet ' in r.stdout
        except Exception:
            return False

    def _check_camera(self):
        """
        USB UVC カメラの capture デバイスが接続されているか判定。
        Raspberry Pi の内蔵 bcm2835-isp/codec や rpi-hevc-dec は
        カメラ非接続時にも /dev/video10-31 として常時存在するため、
        sysfs の name から USB カメラ (typically ELECOM Webcam 等) を選別する。
        (2026-08-13 修正: 従来の glob('/dev/video*') は常に True を返していた)
        """
        try:
            for entry in os.listdir('/sys/class/video4linux'):
                name_path = f'/sys/class/video4linux/{entry}/name'
                if not os.path.isfile(name_path):
                    continue
                with open(name_path) as f:
                    name = f.read().strip().lower()
                # Pi 内蔵デバイスは除外
                if name.startswith('bcm2835-') or name.startswith('rpi-'):
                    continue
                # その他の名前 = USB カメラ (UVC) 等
                return True
        except Exception as e:
            logger.debug(f"Camera detection error: {e}")
        return False

    # ------------------- RSSI → バー レベル -------------------

    @staticmethod
    def rssi_to_bar_level(rssi):
        if rssi is None:
            return 0
        try:
            r = int(rssi)
        except (TypeError, ValueError):
            return 0
        if r > -50: return 4
        if r > -60: return 3
        if r > -70: return 2
        if r > -80: return 1
        return 0

    # ------------------- 行組み立て -------------------

    def _write_row_bytes(self, row, byte_list):
        """1 行分のバイト列を LCD の指定行に書き込み (20 chars 固定)"""
        # ljust with space, truncate to LCD_COLS
        padded = list(byte_list[:LCD_COLS])
        while len(padded) < LCD_COLS:
            padded.append(ord(' '))

        self.lcd.cursor_pos = (row, 0)
        for b in padded:
            try:
                self.lcd.write(b)
            except Exception:
                self.lcd.write(ord('?'))

    def _build_line1(self):
        """日付+時刻 (20 chars 全 ASCII)"""
        s = datetime.now().strftime('%Y/%m/%d  %H:%M:%S')
        return [ord(c) for c in s]

    def _build_line2(self, info, page_txt):
        """
        状態 + アイコン (20 chars):
          Active   : "AP[6] WAN[7] CAM[5] 1/2 "
          Inactive : "APx WANx CAMx 1/2 "  ('x' = 未接続の視覚マーカー)

          [6] = AP アイコン, [7] = WLAN 地球, [5] = CAMERA
          'x' (0x78) = HD44780 標準 ASCII、× に近い形

        (2026-08-13 更新: 未接続を空白ではなく 'x' に変更、現地で「接続なし」を即認識)
        """
        MARK_OFF = ord('x')  # 未接続マーカー (半角 x)

        result = []
        # "AP" + status
        result += [ord('A'), ord('P')]
        result.append(6 if info['ap_running'] else MARK_OFF)
        result.append(ord(' '))
        # "WAN" + status
        result += [ord('W'), ord('A'), ord('N')]
        result.append(7 if info['wlan0_ok'] else MARK_OFF)
        result.append(ord(' '))
        # "CAM" + status
        result += [ord('C'), ord('A'), ord('M')]
        result.append(5 if info['camera_present'] else MARK_OFF)
        result.append(ord(' '))
        # ページ番号 or センサー数
        for c in page_txt:
            result.append(ord(c))
        return result

    def _build_sensor_line(self, s, view_mode='rssi'):
        """
        センサー 1 行 (20 chars):
          view_mode='rssi': "<name 10> <temp 4>C <rssi_icon>   "
          view_mode='age' : "<name 10> <temp 4>C <age 4>"
          nickname → 全角カナは半角化、漢字は '.'

        (2026-08-09 更新: view_mode 追加、末尾を RSSI バー ↔ 経過時間で交互表示)
        """
        # 名前 (nickname > sensor_id > device_id)
        name_raw = (s.get('nickname')
                    or s.get('sensor_id')
                    or s.get('device_id')
                    or '?')
        name_bytes = nickname_to_lcd_bytes(name_raw)
        # 10 文字に切詰め or 空白パディング
        if len(name_bytes) > 10:
            name_bytes = name_bytes[:10]
        else:
            name_bytes = name_bytes + [ord(' ')] * (10 - len(name_bytes))

        # 温度
        temp = s.get('temperature')
        if temp is None:
            temp = s.get('temp')
        try:
            t = float(temp)
            if -9.9 <= t <= 99.9:
                temp_str = f'{t:4.1f}'
            else:
                temp_str = f'{t:4.0f}'
        except (TypeError, ValueError):
            temp_str = '--.-'
        temp_bytes = [ord(c) for c in temp_str]

        # 末尾表示 (RSSI バー or 経過時間)
        if view_mode == 'age':
            # timestamp から経過秒を計算 → 4 char に整形
            ts_dt = parse_timestamp(s.get('timestamp'))
            if ts_dt is None:
                age_str = ' ---'
            else:
                age_sec = (datetime.now() - ts_dt).total_seconds()
                age_str = format_age(age_sec)
            # age は 4 文字なので、name(10)+" "(1)+temp(4)+"C"(1)+age(4) = 20
            tail_bytes = [ord(c) for c in age_str[:4].rjust(4)]
            result = list(name_bytes) + [ord(' ')] + temp_bytes + [ord('C')] + tail_bytes
        else:
            # RSSI → バーアイコン (従来通り)
            rssi = s.get('rssi')
            if rssi is None:
                rssi = s.get('signal_strength')
            bar_level = self.rssi_to_bar_level(rssi)
            rssi_icon = bar_level  # slot 0-4
            # name(10) + " "(1) + temp(4) + "C"(1) + " "(1) + rssi(1) + "  "(2 padding) = 20
            result = (list(name_bytes) + [ord(' ')] + temp_bytes
                      + [ord('C'), ord(' '), rssi_icon, ord(' '), ord(' ')])
        return result

    # ------------------- 描画 -------------------

    def draw(self, info):
        sensors = info['sensors']

        # ページ計算
        if len(sensors) > SENSORS_PER_PAGE:
            pages = -(-len(sensors) // SENSORS_PER_PAGE)
            page = self.rotation_page % pages
            start = page * SENSORS_PER_PAGE
            visible = sensors[start:start + SENSORS_PER_PAGE]
            page_txt = f'{page + 1}/{pages}'
        else:
            visible = sensors[:SENSORS_PER_PAGE]
            page_txt = f'{len(sensors)}sen' if len(sensors) > 0 else 'nosen'

        if not info['flask_alive']:
            page_txt = 'FLASK'

        # 4 行を書き込み
        self._write_row_bytes(0, self._build_line1())
        self._write_row_bytes(1, self._build_line2(info, page_txt))

        sensor_lines = [self._build_sensor_line(s, self.view_mode) for s in visible]
        while len(sensor_lines) < 2:
            sensor_lines.append([ord(' ')] * LCD_COLS)

        self._write_row_bytes(2, sensor_lines[0])
        self._write_row_bytes(3, sensor_lines[1])

    # ------------------- メインループ -------------------

    def run(self):
        logger.info('LCD display loop started')

        # 起動メッセージ (Pi の IP を出す)
        try:
            ip = subprocess.check_output(
                ['hostname', '-I'], text=True, timeout=1
            ).split()[0]
        except Exception:
            ip = '?.?.?.?'

        self.lcd.clear()
        self._write_row_bytes(0, [ord(c) for c in 'Temp Monitor Booting'])
        self._write_row_bytes(1, [ord(c) for c in f'Pi IP: {ip}'])
        self._write_row_bytes(2, [ord(c) for c in 'Dashboard http://'])
        self._write_row_bytes(3, [ord(c) for c in f'{ip}:5000/'])
        time.sleep(3)

        last_rotation = 0.0
        last_view_toggle = 0.0
        try:
            while True:
                now = time.time()
                if now - last_rotation >= ROTATION_SEC:
                    self.rotation_page += 1
                    last_rotation = now
                # view_mode を VIEW_TOGGLE_SEC ごとに交互反転
                if now - last_view_toggle >= VIEW_TOGGLE_SEC:
                    self.view_mode = 'age' if self.view_mode == 'rssi' else 'rssi'
                    last_view_toggle = now

                try:
                    info = self.get_status()
                    self.draw(info)
                except Exception as e:
                    logger.error(f'Draw error: {e}', exc_info=True)

                time.sleep(REFRESH_SEC)
        except KeyboardInterrupt:
            logger.info('Stopped by user')
        finally:
            try:
                self.lcd.clear()
                self._write_row_bytes(0, [ord(c) for c in 'Display stopped'])
                time.sleep(1)
                self.lcd.close(clear=True)
            except Exception:
                pass


def main():
    if not JACONV_AVAILABLE:
        logger.warning("jaconv not installed. Full-width kana → half-width conversion disabled.")
        logger.warning("Install with: pip install jaconv")

    try:
        display = LCDDisplay()
    except Exception as e:
        logger.error(f'LCD init failed: {e}')
        logger.error('Check: 1) I2C enabled, 2) Wiring, 3) LCD_I2C_ADDR env var')
        sys.exit(1)
    display.run()


if __name__ == '__main__':
    main()
