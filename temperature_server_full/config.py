"""
temperature_server/config.py
アプリケーション設定
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

class Config:
    """アプリケーション設定クラス"""

    # ===== Flask設定 =====
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))

    # ===== セキュリティ =====
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # ===== WiFi設定 =====
    AP_INTERFACE = os.getenv('AP_INTERFACE', 'wlan1')
    STATION_INTERFACE = os.getenv('STATION_INTERFACE', 'wlan0')
    AP_SSID = os.getenv('AP_SSID', 'YOUR_AP_SSID_HERE')
    AP_PASSWORD = os.getenv('AP_PASSWORD', 'YOUR_AP_PASSWORD_HERE')
    AP_IP = os.getenv('AP_IP', '192.168.4.1')
    AP_DHCP_START = os.getenv('AP_DHCP_START', '192.168.4.2')
    AP_DHCP_END = os.getenv('AP_DHCP_END', '192.168.4.254')

    # ===== ディレクトリ設定 =====
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / 'data'
    LOGS_DIR = BASE_DIR / 'logs'

    # ディレクトリを作成
    DATA_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    # ===== メモリ監視設定 =====
    MEMORY_THRESHOLD = int(os.getenv('MEMORY_THRESHOLD', 80))  # %
    MEMORY_CHECK_INTERVAL = int(os.getenv('MEMORY_CHECK_INTERVAL', 300))  # 秒

    # ===== WiFi監視設定 =====
    WIFI_CHECK_INTERVAL = int(os.getenv('WIFI_CHECK_INTERVAL', 600))  # 秒

    # ===== ログ設定 =====
    LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', 30))
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', 10 * 1024 * 1024))  # 10MB
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', 5))

    # ===== CORS設定 =====
    ALLOWED_ORIGINS = os.getenv(
        'ALLOWED_ORIGINS',
        'http://localhost:3000,http://192.168.4.1:5000,http://127.0.0.1:5000'
    ).split(',')

    # ===== シリアル通信設定（USB/Serial経由のESP32データ受信） =====
    SERIAL_ENABLED = os.getenv('SERIAL_ENABLED', 'True').lower() == 'true'
    SERIAL_PORT = os.getenv('SERIAL_PORT', None)  # None=自動検出、例: '/dev/ttyUSB0'
    SERIAL_BAUDRATE = int(os.getenv('SERIAL_BAUDRATE', 115200))  # ボーレート
    SERIAL_TIMEOUT = float(os.getenv('SERIAL_TIMEOUT', 1.0))  # タイムアウト（秒）

