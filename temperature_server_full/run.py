#!/usr/bin/env python3
"""
temperature_server/run.py
アプリケーション起動スクリプト

起動時の処理:
1. データベース初期化
2. シリアルリーダー起動 (SERIAL_ENABLED=True の時のみ)
3. Flask Webサーバー起動

コード監査 2026-07-17:
    - 元コードには main() が 2 回定義されていた (line 32 と line 92)。
      Python の後勝ちで line 92 版のみ動作、line 32 版は完全なデッドコード。
      → 削除して単一化。
    - services/serial_reader を無条件 import していた (line 27)。
      → SERIAL_ENABLED=True の時だけ import する遅延読み込みに変更。
        pyserial が未インストールの環境でも起動できるようにする防御策。
"""

import sys
from pathlib import Path
import os

# 環境変数設定
os.environ.setdefault('FLASK_ENV', 'production')

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import Config
from database.models import init_database, migrate_add_rssi_battery
from logger import setup_logger
from app import create_app

logger = setup_logger('main')

# グローバル変数 (シリアルリーダー)
serial_reader = None


def start_serial_reader():
    """
    シリアルリーダーを起動 (USB/Serial 経由の ESP32 データ受信)。

    SERIAL_ENABLED=False の時は import 自体を実行しない (遅延 import)。
    これにより pyserial 未インストール環境でも Flask 本体は起動できる。
    """
    global serial_reader

    if not Config.SERIAL_ENABLED:
        logger.info("Serial reader is disabled (SERIAL_ENABLED=False)")
        return

    # ここで初めて import (遅延 import)
    try:
        from services.serial_reader import create_serial_reader
    except ImportError as e:
        logger.error(f"Failed to import serial_reader (pyserial not installed?): {e}")
        return

    try:
        logger.info("Starting serial reader...")
        serial_reader = create_serial_reader(Config)

        if serial_reader.port is None:
            logger.warning("No serial port found. Check USB connection.")
            serial_reader = None
            return

        serial_reader.start()
        logger.info(f"Serial reader started on {serial_reader.port}")

    except Exception as e:
        logger.error(f"Failed to start serial reader: {e}", exc_info=True)
        serial_reader = None


def stop_serial_reader():
    """シリアルリーダーを停止"""
    global serial_reader

    if serial_reader:
        try:
            serial_reader.stop()
            logger.info("Serial reader stopped")
        except Exception as e:
            logger.error(f"Error stopping serial reader: {e}")


def main():
    """アプリケーション起動"""
    try:
        # データベース初期化
        logger.info("Initializing database...")
        init_database()
        migrate_add_rssi_battery()

        # シリアルリーダー起動 (SERIAL_ENABLED=False なら何もしない)
        start_serial_reader()

        # Flask アプリを作成
        logger.info("Creating Flask application...")
        app = create_app()

        # 起動
        logger.info(f"Starting server on {Config.FLASK_HOST}:{Config.FLASK_PORT}")
        print(f"\nTemperature Server Started!")
        print(f"Dashboard:  http://{Config.FLASK_HOST}:{Config.FLASK_PORT}/")
        print(f"API:        http://{Config.FLASK_HOST}:{Config.FLASK_PORT}/api/")
        print(f"Management: http://{Config.FLASK_HOST}:{Config.FLASK_PORT}/management\n")

        if Config.SERIAL_ENABLED and serial_reader:
            print(f"Serial Reader: {serial_reader.port} @ {serial_reader.baudrate} baud\n")

        app.run(
            host=Config.FLASK_HOST,
            port=Config.FLASK_PORT,
            debug=Config.FLASK_DEBUG,
            threaded=True
        )

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        stop_serial_reader()


if __name__ == '__main__':
    main()
