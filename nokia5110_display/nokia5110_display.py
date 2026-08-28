"""
Nokia 5110 (PCD8544) 温度モニタリング状態表示

Pi 本体に取り付けた 84x48 モノクロ LCD に以下を表示:
  - 日付・時刻
  - AP (wlan1 hostapd) 稼働状態
  - wlan0 (ビル WiFi) 接続状態
  - USB カメラ接続 (/dev/video* 存在で判定)
  - 各センサーの瞬時温度と RSSI バー
  - センサーが 3 台超なら 5 秒間隔でローテーション

依存 (pip):
  - luma.lcd, Pillow, requests, RPi.GPIO, spidev

Pi 側前提:
  - SPI 有効化 (sudo raspi-config → Interface Options → SPI)
  - 日本語フォント (sudo apt install fonts-noto-cjk fonts-mplus)

配線 (詳細は README.md):
  Nokia 5110  →  Pi (BCM)
  VCC         →  3.3V
  GND         →  GND
  DIN (MOSI)  →  GPIO10 (Pin 19)
  CLK (SCLK)  →  GPIO11 (Pin 23)
  DC          →  GPIO23 (Pin 16)
  CE  (SCE)   →  GPIO8  (Pin 24, SPI0 CE0)
  RST         →  GPIO25 (Pin 22)
  BL  (LED)   →  3.3V or GPIO18
"""

import os
import time
import glob
import subprocess
import logging
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from luma.core.interface.serial import spi
from luma.lcd.device import pcd8544


# ============================================================
#  設定 (環境変数でオーバーライド可)
# ============================================================
FLASK_URL          = os.getenv('FLASK_URL', 'http://localhost:5000')
REFRESH_INTERVAL   = float(os.getenv('DISPLAY_REFRESH_SEC', '2'))   # 全体更新
ROTATION_INTERVAL  = float(os.getenv('DISPLAY_ROTATE_SEC', '5'))    # ローテーション
SENSORS_PER_PAGE   = int(os.getenv('DISPLAY_SENSORS_PER_PAGE', '3'))

# フォント (存在する最初のものを使う)
FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/mplus/mplus-1p-regular.ttf',
    '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',   # 最後の砦 (kanji 不可)
]
FONT_ASCII_SIZE = int(os.getenv('FONT_ASCII_SIZE', '8'))    # 日時・状態用
FONT_KANJI_SIZE = int(os.getenv('FONT_KANJI_SIZE', '10'))   # センサー名用

# GPIO ピン (BCM)
SPI_PORT   = 0
SPI_DEVICE = 0
GPIO_DC    = int(os.getenv('NOKIA_GPIO_DC', '23'))
GPIO_RST   = int(os.getenv('NOKIA_GPIO_RST', '25'))

# PCD8544 コントラスト (0-127、実機で調整)
CONTRAST = int(os.getenv('NOKIA_CONTRAST', '60'))


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger('nokia5110')


def find_font():
    """使えるフォントを探して返す"""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


class NokiaDisplay:
    def __init__(self):
        # SPI + PCD8544 初期化
        serial = spi(
            port=SPI_PORT,
            device=SPI_DEVICE,
            gpio_DC=GPIO_DC,
            gpio_RST=GPIO_RST,
        )
        self.device = pcd8544(serial, rotate=0)
        self.device.contrast(CONTRAST)
        self.width = self.device.width    # 84
        self.height = self.device.height  # 48

        # フォント読込
        font_path = find_font()
        if font_path:
            self.font_ascii = ImageFont.truetype(font_path, FONT_ASCII_SIZE)
            self.font_kanji = ImageFont.truetype(font_path, FONT_KANJI_SIZE)
            logger.info(f"Using font: {font_path} (ASCII {FONT_ASCII_SIZE}px, JP {FONT_KANJI_SIZE}px)")
        else:
            logger.warning("No TrueType font found, using default (Kanji will not render)")
            self.font_ascii = ImageFont.load_default()
            self.font_kanji = self.font_ascii

        self.rotation_page = 0

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
        return len(glob.glob('/dev/video*')) > 0

    # ------------------- アイコン ヘルパー -------------------

    def rssi_to_bars(self, rssi):
        """RSSI 値を 0-4 のバー数に変換"""
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

    def draw_rssi_bars(self, draw, x, y, bars):
        """RSSI バーを (x, y) 起点、幅 8px×高さ 8px の 4 本バーで描画"""
        for i in range(4):
            bar_h = (i + 1) * 2                # 2, 4, 6, 8 pixel
            xi = x + i * 2                     # 2 pixel 間隔
            if bars > i:
                draw.rectangle(
                    [xi, y + (8 - bar_h), xi + 1, y + 7],
                    fill=1
                )
            else:
                # 未満は base line だけ (省略でもよい)
                draw.point([xi, y + 7], fill=1)

    def draw_ap_icon(self, draw, x, y, active):
        """AP アイコン (小さいアンテナのようなグリフ)"""
        if active:
            # 塗りつぶし丸っぽい
            draw.rectangle([x, y + 2, x + 5, y + 5], fill=1)
        else:
            draw.rectangle([x, y + 2, x + 5, y + 5], outline=1)

    def draw_camera_icon(self, draw, x, y, present):
        """カメラアイコン (小さいカメラ pixmap)"""
        # 8x6 pixel simple camera glyph
        # 本体
        draw.rectangle([x, y + 2, x + 7, y + 7], outline=1)
        # レンズ
        if present:
            draw.rectangle([x + 3, y + 3, x + 5, y + 6], fill=1)
        # フラッシュ
        draw.point([x + 6, y + 1], fill=1)

    # ------------------- 描画 -------------------

    def draw_frame(self, info):
        img = Image.new('1', (self.width, self.height), 0)
        draw = ImageDraw.Draw(img)

        # === 行 1 (y=0, 高さ ~8): 日時 + AP アイコン ===
        now = datetime.now().strftime('%m/%d %H:%M')
        draw.text((0, 0), now, font=self.font_ascii, fill=1)
        # AP ラベル + アイコン (右上)
        draw.text((60, 0), 'AP', font=self.font_ascii, fill=1)
        self.draw_ap_icon(draw, 76, 0, info['ap_running'])

        # === 行 2 (y=9, 高さ ~8): wlan0 状態 + CAM アイコン + Flask 状態 ===
        wlan_label = 'WAN' + (':o' if info['wlan0_ok'] else ':x')
        draw.text((0, 9), wlan_label, font=self.font_ascii, fill=1)
        # カメラ (右)
        draw.text((40, 9), 'CAM', font=self.font_ascii, fill=1)
        self.draw_camera_icon(draw, 62, 9, info['camera_present'])
        # Flask 生死は右端に "!" で警告
        if not info['flask_alive']:
            draw.text((78, 9), '!', font=self.font_ascii, fill=1)

        # === セパレータ ライン (y=17) ===
        draw.line([(0, 17), (self.width - 1, 17)], fill=1)

        # === センサー行 (y=19 〜、10px 間隔で 3 行) ===
        sensors = info['sensors']
        pages = max(1, -(-len(sensors) // SENSORS_PER_PAGE))  # ceil div
        if len(sensors) > SENSORS_PER_PAGE:
            page = self.rotation_page % pages
            start = page * SENSORS_PER_PAGE
            visible = sensors[start:start + SENSORS_PER_PAGE]
        else:
            visible = sensors[:SENSORS_PER_PAGE]

        y = 19
        for s in visible:
            name = (s.get('nickname')
                    or s.get('sensor_name')
                    or s.get('sensor_id')
                    or '?')
            # 幅制限 (漢字約 4-5 文字、ASCII 約 7-8 文字)
            display_name = name[:5]

            temp = s.get('temperature')
            if temp is None:
                temp = s.get('temp')
            try:
                temp_str = f'{float(temp):.1f}' if temp is not None else '--.-'
            except (TypeError, ValueError):
                temp_str = '--.-'

            rssi = s.get('rssi')
            bars = self.rssi_to_bars(rssi)

            # 名前 (kanji フォント)
            draw.text((0, y), display_name, font=self.font_kanji, fill=1)
            # 温度 (ASCII フォント、右寄せ位置)
            draw.text((44, y + 1), f'{temp_str}°', font=self.font_ascii, fill=1)
            # RSSI バー (右端)
            self.draw_rssi_bars(draw, 68, y + 1, bars)

            y += 10
            if y >= self.height:
                break

        # ページ位置インジケーター (右下、複数ページある場合)
        if len(sensors) > SENSORS_PER_PAGE:
            page = self.rotation_page % pages
            txt = f'{page + 1}/{pages}'
            draw.text((self.width - 15, self.height - 8), txt,
                      font=self.font_ascii, fill=1)

        # 描画確定
        self.device.display(img)

    # ------------------- メインループ -------------------

    def run(self):
        logger.info('Nokia 5110 display started')
        last_rotation = 0.0
        try:
            while True:
                now = time.time()
                if now - last_rotation >= ROTATION_INTERVAL:
                    self.rotation_page += 1
                    last_rotation = now

                try:
                    info = self.get_status()
                    self.draw_frame(info)
                except Exception as e:
                    logger.error(f'Draw frame error: {e}', exc_info=True)

                time.sleep(REFRESH_INTERVAL)
        except KeyboardInterrupt:
            logger.info('Display stopped by user')
        finally:
            self.device.cleanup()


def main():
    display = NokiaDisplay()
    display.run()


if __name__ == '__main__':
    main()
