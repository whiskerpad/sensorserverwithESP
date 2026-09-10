"""
第8回 温度サーバー最小版
  HTTP POST と USB シリアルの 2 経路を受けて SQLite に保存する

  起動: python3 ~/tempserver/app.py
"""
import glob
import os
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import serial
from flask import Flask, request, jsonify, render_template

# ===== 設定 =====
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "temperature.db"

SERIAL_PORT    = os.environ.get("SERIAL_PORT", "auto")   # "auto" で自動検出
                               # CH340 / CP2102 / FT232 の変換基板経由なら ttyUSB*
                               # 分からなければ  ls /dev/ttyACM* /dev/ttyUSB*  で確認
SERIAL_BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "90"))   # 4 章で使う

app = Flask(__name__)

def find_serial_port():
    """繋がっているシリアルポートを 1 つ返す。無ければ None。

    CH340 / CH341 / FT232 / CP2102 などの USB-シリアル変換チップは、
    ドライバは別々でも Linux からはどれも /dev/ttyUSB* に見える。
    XIAO ESP32-C3 のように USB を自前で持つチップは /dev/ttyACM*。
    両方を見に行くので、変換チップの種類を気にする必要はない。
    """
    if SERIAL_PORT != "auto":
        return SERIAL_PORT
    ports = sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None



# ===== データベース =====
@contextmanager
def db():
    """1 回の操作ごとに接続を開いて閉じる。
    Flask のスレッドとシリアル読取りスレッドが別々に呼ぶので、
    接続を使い回さないほうが安全。"""
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS temperatures (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id       TEXT NOT NULL,
                temperature     REAL NOT NULL,
                voltage         REAL,
                rssi            INTEGER,
                battery_mode    INTEGER DEFAULT 0,
                connection_type TEXT DEFAULT 'unknown',
                timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_device_timestamp
            ON temperatures(device_id, timestamp DESC)
        """)
        # 表示名テーブル (第9回 2.1)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_nicknames (
                device_id  TEXT PRIMARY KEY,
                nickname   TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)


def save_reading(data, conn_type):
    """2 経路の受信データを 1 か所で正規化して保存する。
    戻り値: (成功したか, メッセージ)"""
    device_id = data.get("device_id")
    temp = data.get("temperature", data.get("temp"))

    if not device_id:
        return False, "device_id がありません"
    if temp is None:
        return False, "temperature がありません"
    try:
        temp = float(temp)
    except (TypeError, ValueError):
        return False, f"temperature が数値ではありません: {temp!r}"

    # 明らかな異常値は捨てる (DS18B20 の測定範囲は -55〜+125℃)
    if not (-55.0 <= temp <= 125.0):
        return False, f"温度が測定範囲外です: {temp}"

    rssi = data.get("rssi", data.get("signal_strength"))
    voltage = data.get("voltage")
    battery = 1 if data.get("battery_mode") else 0

    with db() as conn:
        conn.execute("""
            INSERT INTO temperatures
                (device_id, temperature, voltage, rssi, battery_mode, connection_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (device_id, round(temp, 2), voltage, rssi, battery, conn_type))

    print(f"[{conn_type}] {device_id}  {temp:.2f}℃  rssi={rssi}  volt={voltage}",
          flush=True)
    return True, "ok"


# ===== 経路 1: HTTP POST (第6回の WiFi 子機) =====
@app.post("/api/temperature")
def api_temperature():
    data = request.get_json(silent=True) or {}
    ok, msg = save_reading(data, "wifi")
    if ok:
        return jsonify(status="ok")
    print(f"[wifi] 受信を拒否: {msg} / 生データ: {request.get_data(as_text=True)[:200]}",
          flush=True)
    return jsonify(status="error", reason=msg), 400


# ===== 経路 2: USB シリアル (第7回の ESP-NOW Master) =====
def serial_loop():
    """別スレッドで動く。ポートが消えても開き直す。"""
    while True:
        port = find_serial_port()          # 接続のたびに探し直す
        if port is None:
            print("[serial] シリアルポートが見つかりません。5 秒後に再試行",
                  flush=True)
            time.sleep(5)
            continue

        try:
            ser = serial.Serial(port, SERIAL_BAUD, timeout=5)
            print(f"[serial] {port} を開きました", flush=True)
        except Exception as e:
            print(f"[serial] {port} を開けません ({e})。5 秒後に再試行", flush=True)
            time.sleep(5)
            continue

        try:
            while True:
                raw = ser.readline().decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                if raw.startswith("#"):        # Master の人間向けメッセージ
                    print(f"[serial] {raw}", flush=True)
                    continue
                if not raw.startswith("{"):    # JSON 以外は捨てる
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"[serial] JSON として読めません: {raw[:100]}", flush=True)
                    continue

                kind = data.get("type")

                if kind in ("master_hello", "master_status"):
                    print(f"[serial] Master 生存確認: {data.get('device_id')} "
                          f"{data.get('mac', '')}", flush=True)

                elif "sensors" in data:
                    # 温度データ。Master が 1 秒ごとにまとめて配列で送ってくる。
                    # 注意: この階層の device_id は Master 自身の ID。
                    #       子機の ID は sensors[].sensor_id のほう。
                    for s in data["sensors"]:
                        save_reading({
                            "device_id":    s.get("sensor_id"),
                            "temperature":  s.get("temperature", s.get("temp")),
                            "rssi":         s.get("rssi"),
                            "voltage":      s.get("voltage"),
                            "battery_mode": s.get("battery_mode"),
                        }, "espnow")

                else:
                    print(f"[serial] 解釈できない JSON: {raw[:100]}", flush=True)

        except Exception as e:
            print(f"[serial] 切断されました ({e})。開き直します", flush=True)
        finally:
            try:
                ser.close()
            except Exception:
                pass
        time.sleep(2)


# ===== 表示用 API =====
@app.get("/api/latest")
def api_latest():
    """デバイスごとの最新 1 件 (表示名を付けて返す)"""
    with db() as conn:
        rows = conn.execute("""
            SELECT t.*, n.nickname AS nickname
            FROM temperatures t
            JOIN (SELECT device_id, MAX(id) AS max_id
                  FROM temperatures GROUP BY device_id) m
              ON t.id = m.max_id
            LEFT JOIN device_nicknames n ON n.device_id = t.device_id
            ORDER BY COALESCE(n.nickname, t.device_id)
        """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/history")
def api_history():
    """直近 N 時間の履歴を device_id ごとにまとめて返す"""
    hours = request.args.get("hours", default=24, type=int)
    hours = max(1, min(hours, 24 * 30))

    with db() as conn:
        rows = conn.execute("""
            SELECT t.device_id,
                   COALESCE(n.nickname, t.device_id) AS label,
                   t.temperature, t.timestamp
            FROM temperatures t
            LEFT JOIN device_nicknames n ON n.device_id = t.device_id
            WHERE t.timestamp >= datetime('now', ?)
            ORDER BY t.timestamp
        """, (f"-{hours} hours",)).fetchall()

    series = {}
    for r in rows:
        entry = series.setdefault(r["device_id"],
                                  {"label": r["label"], "points": []})
        entry["points"].append({"t": r["timestamp"], "v": r["temperature"]})
    return jsonify(series)


@app.get("/")
def dashboard():
    return render_template("index.html")


# ===== 起動 =====
# ===== 表示名 (nickname) の API =====
@app.get("/api/nicknames")
def api_nicknames():
    """登録されている表示名を全部返す"""
    with db() as conn:
        rows = conn.execute("""
            SELECT device_id, nickname, updated_at
            FROM device_nicknames
            ORDER BY device_id
        """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.put("/api/nicknames/<device_id>")
def api_nickname_set(device_id):
    """表示名を設定する (無ければ追加、あれば更新)"""
    data = request.get_json(silent=True) or {}
    nickname = (data.get("nickname") or "").strip()

    if not nickname:
        return jsonify(status="error", reason="nickname が空です"), 400
    if len(device_id) > 100:
        return jsonify(status="error", reason="device_id が長すぎます"), 400
    if len(nickname) > 50:
        return jsonify(status="error", reason="nickname は 50 文字までです"), 400

    with db() as conn:
        conn.execute("""
            INSERT INTO device_nicknames (device_id, nickname, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(device_id) DO UPDATE SET
                nickname   = excluded.nickname,
                updated_at = excluded.updated_at
        """, (device_id, nickname))

    print(f"[nickname] {device_id} -> {nickname}", flush=True)
    return jsonify(status="ok", device_id=device_id, nickname=nickname)


@app.delete("/api/nicknames/<device_id>")
def api_nickname_delete(device_id):
    """表示名を消す。温度データには触らない"""
    with db() as conn:
        deleted = conn.execute(
            "DELETE FROM device_nicknames WHERE device_id = ?",
            (device_id,)
        ).rowcount
    return jsonify(status="ok", device_id=device_id, deleted=deleted)


@app.get("/manage")
def manage():
    return render_template("manage.html")

# ===== 古いデータの掃除 =====
def purge_old_rows(days=None):
    """指定日数より古い行を消す。消した件数を返す"""
    days = RETENTION_DAYS if days is None else days
    with db() as conn:
        deleted = conn.execute(
            "DELETE FROM temperatures WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",)
        ).rowcount
    if deleted:
        print(f"[purge] {days} 日より古い {deleted} 件を削除しました", flush=True)
    return deleted


def purge_loop():
    """1 日 1 回、掃除する。serial_loop と同じく daemon スレッドで回す"""
    while True:
        try:
            purge_old_rows()
        except Exception as e:
            print(f"[purge] 失敗しました ({e})", flush=True)
        time.sleep(24 * 60 * 60)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=serial_loop, daemon=True).start()
    threading.Thread(target=purge_loop,  daemon=True).start()   # ← 追加
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
