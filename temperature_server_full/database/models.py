"""
temperature_server/database/models.py
SQLite スキーマ定義

2026-07-17: device_nicknames テーブル追加 (nickname 機能)
"""

import sqlite3
from pathlib import Path
from config import Config

DB_PATH = Path(Config.DATA_DIR) / "temperature.db"


def init_database():
    """データベーステーブルを初期化"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # 温度データテーブル
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS temperatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL,
            sensor_name TEXT,
            temperature REAL NOT NULL,
            humidity REAL,
            rssi INTEGER,
            battery_mode INTEGER DEFAULT 0,
            connection_type TEXT DEFAULT 'unknown',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # インデックス作成 (クエリ高速化)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sensor_timestamp
        ON temperatures(sensor_id, timestamp DESC)
    """)

    # 2026-08-16 監査: 以下 4 テーブルは Python コード側で参照ゼロだったため CREATE 廃止
    #   - wifi_connections (WiFi 接続履歴、書込みコード無し)
    #   - system_logs      (SystemLogQueries 廃止済、常時空)
    #   - temperature_alerts (アラート機構未実装)
    #   - settings         (定数化されており DB 参照ゼロ)
    # 既存 DB に残っているテーブルは無害なので DROP しない。新規 DB には作らない。

    # デバイス表示名 (nickname) テーブル (2026-07-17 追加)
    # sensor_id は temperatures.sensor_id と対応、nickname は
    # 「冷却塔1」「外気温」などの人間可読名。
    # 過去データは変えず、表示時のみ nickname を優先。
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_nicknames (
            sensor_id TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ESP-NOW Master 機の識別情報 (2026-08-15 追加)
    # 子機スケッチ書込み時に MAC をコピペするために保持する。
    # first_seen  = 初めて hello を受け取った時刻
    # last_seen   = 最後に hello/status を受け取った時刻 (heartbeat)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS masters (
            device_id  TEXT PRIMARY KEY,
            mac        TEXT NOT NULL,
            firmware   TEXT,
            first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def migrate_add_rssi_battery():
    """既存のテーブルに rssi と battery_mode カラムを追加 (旧 DB 互換)"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE temperatures ADD COLUMN rssi INTEGER")
    except sqlite3.OperationalError:
        pass  # 列が既に存在

    try:
        cursor.execute("ALTER TABLE temperatures ADD COLUMN battery_mode INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def get_connection():
    """スレッドセーフな DB 接続を取得"""
    conn = sqlite3.connect(str(DB_PATH), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
