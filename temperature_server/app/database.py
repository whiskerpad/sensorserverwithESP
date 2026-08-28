"""SQLite ラッパー層。

参照リポジトリ (opticalbreeze/dual-wifi-temperature-monitoring) の 2 つの問題を修正:

問題 1: ネストした db_lock 取得によるデッドロック
    元コード: get_all_latest() が db_lock 保有中に get_latest_reading() を N 回呼ぶ
    修正: 1 つの SQL クエリで全センサー最新値を取得 (INNER JOIN + MAX(id) サブクエリ)

問題 2: タイムスタンプ形式のミスマッチ (ISO 形式 vs 素朴形式)
    元コード: 挿入時 strftime('%Y-%m-%d %H:%M:%S')、クエリ時 datetime.now().isoformat()
    -> テキスト比較で「T」が「 」より大きく、範囲比較が常に偽になる
    修正: 挿入・クエリ両方で strftime に統一し、TS_FORMAT 定数で共有

その他改善:
- Row Factory で dict 変換を簡略化
- インデックス (device_id, received_at) で範囲クエリを高速化
- 欠測 (temp_c IS NULL) は統計から除外
"""
import sqlite3
import threading
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

from flask import current_app

logger = logging.getLogger(__name__)

# シングル ロックで排他制御 (SQLite は複数接続からの書込みで locking を出しがち)
_db_lock = threading.Lock()

# タイムスタンプ形式は挿入とクエリで完全に一致させる (JST 素朴形式)
# システムのタイムゾーンが JST (Asia/Tokyo) 前提。datetime.now() は naive で JST を返す
TS_FORMAT = '%Y-%m-%d %H:%M:%S'


@contextmanager
def _get_conn():
    """SQLite 接続を提供 (with 文用)。ロックタイムアウト 10 秒。"""
    db_path = current_app.config['DB_PATH']
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """スキーマ作成 (存在しなければ)。

    方針 A で /api/temperature エンドポイントを追加したため、
    name (デバイス表示名) と ip_address (固定IP) の列を追加。
    既存 DB との互換性のため、ALTER TABLE ADD COLUMN を try 実行。
    """
    with _db_lock:
        with _get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS readings (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id    TEXT NOT NULL,
                    sensor_index INTEGER,
                    sensor_addr  TEXT,
                    temp_c       REAL,
                    voltage      REAL,
                    battery_pct  REAL,
                    is_battery   INTEGER,
                    rssi_dbm     INTEGER,
                    received_at  TEXT NOT NULL,
                    name         TEXT,
                    ip_address   TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_device_time
                    ON readings(device_id, received_at);
                CREATE INDEX IF NOT EXISTS idx_time
                    ON readings(received_at);
            """)
            # 既存 DB の後方互換: 列がなければ追加 (SQLite の ALTER は列追加のみ可)
            for col_ddl in (
                "ALTER TABLE readings ADD COLUMN name TEXT",
                "ALTER TABLE readings ADD COLUMN ip_address TEXT",
            ):
                try:
                    conn.execute(col_ddl)
                except sqlite3.OperationalError:
                    # 列がすでに存在する場合は無視
                    pass
            conn.commit()
    logger.info("Database initialized: %s", current_app.config['DB_PATH'])


def insert_reading(device_id, sensor_index, sensor_addr, temp_c,
                   voltage, battery_pct, is_battery, rssi_dbm,
                   name=None, ip_address=None):
    """1 レコードを挿入。サーバー側で received_at (JST 素朴形式) を付与。

    Args:
        device_id (str): ESP デバイス識別子
        sensor_index (int|None): DS18B20 の配列インデックス
        sensor_addr (str|None): 64bit ROM (16進16桁)
        temp_c (float|None): 温度 (None = 欠測)
        voltage (float|None): ESP 電源電圧
        battery_pct (float|None): 電池残量 %
        is_battery (bool): バッテリー駆動モードかどうか
        rssi_dbm (int|None): WiFi 電波強度
        name (str|None): デバイス表示名 (/api/temperature 経由の時のみ)
        ip_address (str|None): 固定 IP (/api/temperature 経由の時のみ)

    Returns:
        str: 記録した received_at (フォーマット済み文字列)
    """
    now = datetime.now().strftime(TS_FORMAT)
    with _db_lock:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO readings
                (device_id, sensor_index, sensor_addr, temp_c,
                 voltage, battery_pct, is_battery, rssi_dbm, received_at,
                 name, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                device_id, sensor_index, sensor_addr, temp_c,
                voltage, battery_pct, 1 if is_battery else 0, rssi_dbm, now,
                name, ip_address,
            ))
            conn.commit()
    return now


def get_all_devices_latest():
    """全デバイスの各センサー最新値を 1 クエリで取得。

    デッドロック回避: ロック保有中に N 回クエリせず、単一 SQL で完結させる。
    """
    with _db_lock:
        with _get_conn() as conn:
            cursor = conn.execute("""
                SELECT r.*
                FROM readings r
                INNER JOIN (
                    SELECT device_id, sensor_index, MAX(id) AS max_id
                    FROM readings
                    GROUP BY device_id, sensor_index
                ) latest ON r.id = latest.max_id
                ORDER BY r.device_id, r.sensor_index
            """)
            return [dict(row) for row in cursor.fetchall()]


def get_readings(device_id, hours=24.0):
    """指定デバイスの時間範囲データを時系列順で取得。

    比較値は挿入時と同じ strftime 形式で生成 (問題 2 の修正の要)。
    """
    since = (datetime.now() - timedelta(hours=float(hours))).strftime(TS_FORMAT)
    with _db_lock:
        with _get_conn() as conn:
            cursor = conn.execute("""
                SELECT * FROM readings
                WHERE device_id = ? AND received_at >= ?
                ORDER BY received_at ASC, sensor_index ASC
            """, (device_id, since))
            return [dict(row) for row in cursor.fetchall()]


def get_stats(device_id, hours=24.0):
    """指定デバイスのセンサーごとの統計 (最低・最高・平均・件数)。

    欠測 (temp_c IS NULL) は集計から除外。
    """
    since = (datetime.now() - timedelta(hours=float(hours))).strftime(TS_FORMAT)
    with _db_lock:
        with _get_conn() as conn:
            cursor = conn.execute("""
                SELECT
                    sensor_index,
                    sensor_addr,
                    COUNT(*)     AS count,
                    MIN(temp_c)  AS min_temp,
                    MAX(temp_c)  AS max_temp,
                    AVG(temp_c)  AS avg_temp
                FROM readings
                WHERE device_id = ?
                  AND received_at >= ?
                  AND temp_c IS NOT NULL
                GROUP BY sensor_index, sensor_addr
                ORDER BY sensor_index
            """, (device_id, since))
            return [dict(row) for row in cursor.fetchall()]


def get_device_list():
    """データが存在する全デバイスの ID 一覧。"""
    with _db_lock:
        with _get_conn() as conn:
            cursor = conn.execute("""
                SELECT DISTINCT device_id FROM readings
                ORDER BY device_id
            """)
            return [row['device_id'] for row in cursor.fetchall()]


def count_all():
    """総レコード数 (health check 用)。"""
    with _db_lock:
        with _get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) AS c FROM readings")
            return cursor.fetchone()['c']
