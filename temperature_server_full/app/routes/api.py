"""
temperature_server/app/routes/api.py
API エンドポイント (/api/*)

コード監査 2026-07-17:
    Item 9:  /api/test-delete を削除 (デバッグ用、本番不要)
    Item 10: request_id を utils/request_tracing の @trace_request に統一
             (元は各エンドポイントで手作り uuid.uuid4()[:8])
    Item 11: /api/logs を SystemLogQueries から logs/*.log ファイル読み取りに変更
             /api/export/logs も同様
             SystemLogQueries は常時空だった (insert_log() を呼ぶ箇所がないため)
"""

from flask import Blueprint, request, jsonify, Response
from logger import setup_logger
from datetime import datetime
import sys
import subprocess
import io
import csv
import shutil
import urllib.parse
from pathlib import Path

# パス設定
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import Config
from database.queries import TemperatureQueries, NicknameQueries, MasterQueries
from utils.request_tracing import trace_request, get_request_id, log_with_request_id

logger = setup_logger(__name__)
api_bp = Blueprint('api', __name__)

# ============================================================
#  device_id 重複検知用の in-memory マップ (2026-07-28 追加)
#  { sensor_id: last_ip_address } を保持し、同じ sensor_id で
#  違う ip_address からの POST を検出したら WARN ログを出す。
#  Flask 再起動でリセット (永続化不要、警告目的のみ)。
# ============================================================
_last_ip_per_sensor = {}


# ============================================================
#  POST /api/temperature - ESP からの温度データ受信
# ============================================================
@api_bp.route('/temperature', methods=['POST'])
@trace_request
def receive_temperature():
    """ESP32/ESP8266 からの温度データ受信"""
    rid = get_request_id()

    raw_body = request.get_data(as_text=True)
    log_with_request_id(f"POST /api/temperature body: {raw_body[:500]}")

    data = request.get_json(force=True, silent=True)
    if not data:
        log_with_request_id(f"JSON decode failed: {raw_body[:200]}", 'warning')
        return jsonify({
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid JSON format",
            "request_id": rid,
        }), 400

    sensor_id = data.get('device_id') or data.get('sensor_id')
    temperature = data.get('temperature') or data.get('temp')

    if not sensor_id or temperature is None:
        log_with_request_id("Missing required fields", 'warning')
        return jsonify({
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Missing required fields: device_id/sensor_id, temperature",
            "request_id": rid,
        }), 400

    try:
        temperature = float(temperature)
        sensor_name = data.get('name') or data.get('sensor_name', 'Unknown')
        humidity = data.get('humidity')
        # 【修正 2026-07-28】ESP-WROOM-02 と ESP32 で送信フィールド名が異なる
        # ため、rssi と signal_strength の両方を受け付ける
        rssi = data.get('rssi')
        if rssi is None:
            rssi = data.get('signal_strength')
        battery_mode = data.get('battery_mode', False)
        connection_type = 'wifi_ap' if rssi is not None else 'esp_now'

        # 【新規 2026-07-28】device_id 重複検知
        # 同じ device_id で違う ip_address からの POST を WARN ログに出す。
        # サイレントに複数チップが同じ device_id を名乗ってしまう事故を
        # 早期発見するため。ip_address が JSON に無ければ検知不能なのでスキップ。
        posted_ip = data.get('ip_address') or request.remote_addr
        if posted_ip:
            prev_ip = _last_ip_per_sensor.get(sensor_id)
            if prev_ip and prev_ip != posted_ip:
                logger.warning(
                    f"[DUPLICATE device_id WARNING] sensor_id='{sensor_id}' "
                    f"was previously reported from {prev_ip}, now from {posted_ip}. "
                    f"Possible cause: two chips share the same device_id, "
                    f"or the chip's DHCP IP changed. Data will still be stored, "
                    f"but the dashboard will merge both chips as one sensor."
                )
            _last_ip_per_sensor[sensor_id] = posted_ip

        log_with_request_id(f"DB insert - {sensor_id}: temp={temperature}C ip={posted_ip}")

        TemperatureQueries.insert_reading(
            sensor_id, temperature, sensor_name, humidity, rssi, battery_mode, connection_type
        )

        return jsonify({
            "status": "success",
            "message": "Data received and stored",
            "device_id": sensor_id,
            "temperature": temperature,
            "request_id": rid,
            "timestamp": datetime.now().isoformat(),
        }), 201

    except Exception as db_error:
        log_with_request_id(f"DB insert error: {db_error}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "DATABASE_ERROR",
            "message": f"Failed to insert data: {str(db_error)}",
            "request_id": rid,
        }), 500


# ============================================================
#  GET /api/sensors - 全センサー最新値
# ============================================================
@api_bp.route('/sensors', methods=['GET'])
@trace_request
def get_all_sensors():
    """全センサーの最新データを取得"""
    rid = get_request_id()
    try:
        sensors = TemperatureQueries.get_all_latest()
        log_with_request_id(f"{len(sensors)} sensors returned")
        return jsonify({
            "status": "success",
            "sensors": sensors,
            "count": len(sensors),
            "request_id": rid,
        })
    except Exception as e:
        log_with_request_id(f"Sensor fetch error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "SENSOR_ERROR",
            "message": "Failed to fetch sensors",
            "request_id": rid,
        }), 500


# ============================================================
#  GET /api/temperature/<sensor_id> - 特定センサーの時間範囲データ
# ============================================================
@api_bp.route('/temperature/<sensor_id>', methods=['GET'])
@trace_request
def get_sensor_data(sensor_id):
    """特定センサーのデータを取得"""
    rid = get_request_id()
    try:
        hours = request.args.get('hours', 24, type=float)
        if hours <= 0 or hours > 8760:
            return jsonify({
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "hours must be between 0 and 8760",
                "request_id": rid,
            }), 400

        readings = TemperatureQueries.get_range(sensor_id, hours)
        stats = TemperatureQueries.get_statistics(sensor_id, hours)

        return jsonify({
            "status": "success",
            "sensor_id": sensor_id,
            "readings": readings,
            "statistics": stats,
            "request_id": rid,
        })
    except Exception as e:
        log_with_request_id(f"Sensor data error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "SENSOR_ERROR",
            "message": f"Failed to fetch sensor data: {sensor_id}",
            "request_id": rid,
        }), 500


# ============================================================
#  GET /api/status - システムステータス
# ============================================================
@api_bp.route('/status', methods=['GET'])
@trace_request
def get_status():
    """システムステータスを取得"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        uptime = datetime.now().timestamp() - psutil.Process(1).create_time()
        sensors = TemperatureQueries.get_all_latest()

        return jsonify({
            "status": "online",
            "timestamp": str(datetime.now()),
            "connected_sensors": len(sensors),
            # 2026-08-16: cpu_percent 追加 (パフォーマンスタブ簡易表示用)
            # interval=None は「前回呼び出しからの累計 CPU 使用率」を即返す (非ブロッキング)
            # 初回だけ意味のある値にするため 0.05 秒サンプル
            "cpu_percent": round(psutil.cpu_percent(interval=0.05), 1),
            "memory_percent": round(mem.percent, 1),
            "memory_used_mb": round(mem.used / 1024 / 1024, 0),
            "memory_total_mb": round(mem.total / 1024 / 1024, 0),
            "disk_percent": round(psutil.disk_usage('/').percent, 1),
            "uptime_seconds": int(uptime),
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
#  GET /api/status/ap - WiFi AP 稼働状況
# ============================================================
def _check_ap_status():
    """WiFi AP の稼働状況を確認 (hostapd と dnsmasq が動いているか)"""
    try:
        r1 = subprocess.run(["/usr/bin/pgrep", "hostapd"], capture_output=True, timeout=5)
        r2 = subprocess.run(["/usr/bin/pgrep", "dnsmasq"], capture_output=True, timeout=5)
        return r1.returncode == 0 and r2.returncode == 0
    except Exception as e:
        logger.warning(f"AP status check failed: {e}")
        return False


@api_bp.route('/status/ap', methods=['GET'])
def get_ap_status():
    """WiFi AP 稼働状況"""
    ap_running = _check_ap_status()
    return jsonify({
        "status": "success",
        "ap_running": ap_running,
        "message": "WiFi AP running" if ap_running else "WiFi AP stopped",
    })


# ============================================================
#  GET /api/logs - ログファイル tail (Item 11: DB → ファイル読み取りに変更)
# ============================================================
@api_bp.route('/logs', methods=['GET'])
@trace_request
def get_logs():
    """ログファイルの末尾 N 行を返す (logs/main.log と logs/app.routes.api.log をマージ)"""
    rid = get_request_id()
    try:
        limit = request.args.get('limit', 50, type=int)
        if limit <= 0 or limit > 5000:
            limit = 50

        log_dir = Config.LOGS_DIR
        # 存在する .log ファイルの末尾を集める
        log_files = sorted(log_dir.glob('*.log'))
        lines = []
        for log_path in log_files:
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    file_lines = f.readlines()[-limit:]
                    for line in file_lines:
                        lines.append({
                            "source": log_path.name,
                            "line": line.rstrip('\n'),
                        })
            except Exception as e:
                logger.warning(f"Failed to read {log_path}: {e}")

        # 全体を最終的に末尾から limit 件に絞る
        lines = lines[-limit:]

        return jsonify({
            "status": "success",
            "logs": lines,
            "count": len(lines),
            "request_id": rid,
        })
    except Exception as e:
        log_with_request_id(f"Log fetch error: {e}", 'error')
        return jsonify({"status": "error", "message": str(e), "request_id": rid}), 500


# ============================================================
#  POST /api/delete-old-data - 古いデータ削除
# ============================================================
@api_bp.route('/delete-old-data', methods=['POST'])
@trace_request
def delete_old_data():
    """指定日数以前のデータを削除"""
    try:
        data = request.get_json() or {}
        days_old = data.get('days_old', 30)
        deleted_count = TemperatureQueries.delete_old_records(days_old)
        return jsonify({
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"{deleted_count} records deleted",
        })
    except Exception as e:
        logger.error(f"delete_old_data error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
#  POST /api/temperature/batch - 複数センサー一括取得 (ダッシュボード用)
# ============================================================
@api_bp.route('/temperature/batch', methods=['POST'])
@trace_request
def get_temperature_batch():
    """複数センサーのデータを一括取得 (間引き対応)"""
    try:
        data = request.get_json()
        if not data or 'sensor_ids' not in data:
            return jsonify({'status': 'error', 'message': 'sensor_ids required'}), 400

        sensor_ids = data.get('sensor_ids', [])
        hours_value = data.get('hours', 24)
        hours = float(hours_value) if hours_value is not None else 24.0

        max_points_value = data.get('max_points')
        if max_points_value is not None:
            max_points = int(max_points_value)
        else:
            max_points = 200 if hours <= 1 else 500

        if not isinstance(sensor_ids, list) or len(sensor_ids) == 0:
            return jsonify({'status': 'error', 'message': 'sensor_ids must be non-empty list'}), 400

        readings_map = TemperatureQueries.get_range_batch(
            sensor_ids, hours, max_points_per_sensor=max_points
        )

        include_stats = data.get('include_stats', False)
        results = {}
        total_points = 0
        for sensor_id in sensor_ids:
            readings = readings_map.get(sensor_id, [])
            result_data = {"readings": readings}
            if include_stats:
                result_data["statistics"] = TemperatureQueries.get_statistics(sensor_id, hours)
            results[sensor_id] = result_data
            total_points += len(readings)

        return jsonify({
            "status": "success",
            "data": results,
            "count": len(results),
            "total_points": total_points,
        })
    except Exception as e:
        logger.error(f"batch fetch error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================
#  GET /api/routes - 登録ルート一覧 (デバッグ用、残置)
# ============================================================
@api_bp.route('/routes', methods=['GET'])
def list_routes():
    """登録された /api/ ルートの一覧"""
    from flask import current_app
    routes = []
    for rule in current_app.url_map.iter_rules():
        if rule.rule.startswith('/api'):
            routes.append({
                "methods": list(rule.methods),
                "rule": rule.rule,
                "endpoint": rule.endpoint,
            })
    return jsonify({
        "status": "success",
        "api_routes": routes,
        "total": len(routes),
    })


# ============================================================
#  DELETE /api/sensors/<sensor_id> - センサーデータ削除
# ============================================================
@api_bp.route('/sensors/<sensor_id>', methods=['DELETE'])
@trace_request
def delete_sensor(sensor_id):
    """特定センサーの全データを削除"""
    rid = get_request_id()
    try:
        sensor_id_decoded = urllib.parse.unquote(sensor_id)
        deleted_count = TemperatureQueries.delete_sensor(sensor_id_decoded)
        log_with_request_id(f"Deleted {deleted_count} records for {sensor_id_decoded}")
        return jsonify({
            "status": "success",
            "sensor_id": sensor_id_decoded,
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} records",
            "request_id": rid,
        }), 200
    except Exception as e:
        log_with_request_id(f"Delete error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "DELETE_ERROR",
            "message": f"Delete failed: {str(e)}",
            "request_id": rid,
            "error_type": type(e).__name__,
        }), 500


# ============================================================
#  GET /api/export/csv - CSV エクスポート
# ============================================================
@api_bp.route('/export/csv', methods=['GET'])
@trace_request
def export_csv():
    """温度データを CSV でエクスポート"""
    rid = get_request_id()
    try:
        hours = request.args.get('hours', 720, type=float)
        sensor_id = request.args.get('sensor_id', None)

        if sensor_id:
            readings = TemperatureQueries.get_range(sensor_id, hours)
        else:
            sensors = TemperatureQueries.get_all_latest()
            readings = []
            for s in sensors:
                readings.extend(TemperatureQueries.get_range(s['sensor_id'], hours))

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'sensor_id', 'sensor_name', 'temperature_C', 'humidity_%',
            'rssi_dBm', 'battery', 'connection_type', 'timestamp',
        ])
        for r in readings:
            writer.writerow([
                r.get('sensor_id', ''),
                r.get('sensor_name', ''),
                r.get('temperature', ''),
                r.get('humidity', ''),
                r.get('rssi', ''),
                'battery' if r.get('battery_mode') else 'ac',
                r.get('connection_type', ''),
                r.get('timestamp', ''),
            ])

        output.seek(0)
        filename = f"temperature_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/csv; charset=utf-8',
            },
        )
    except Exception as e:
        log_with_request_id(f"CSV export error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "EXPORT_ERROR",
            "message": f"CSV export failed: {str(e)}",
            "request_id": rid,
        }), 500


# ============================================================
#  GET /api/export/logs - ログファイル tail をテキストでエクスポート
# ============================================================
@api_bp.route('/export/logs', methods=['GET'])
@trace_request
def export_logs():
    """ログファイル (logs/*.log) をテキストでダウンロード"""
    rid = get_request_id()
    try:
        limit = request.args.get('limit', 1000, type=int)
        level = request.args.get('level', None)  # 'ERROR', 'WARNING', 'INFO'

        log_dir = Config.LOGS_DIR
        log_files = sorted(log_dir.glob('*.log'))

        output = io.StringIO()
        output.write(f"System logs export\n")
        output.write(f"Exported at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        output.write(f"Limit per file: {limit}\n")
        output.write(f"Level filter: {level or 'all'}\n")
        output.write("=" * 80 + "\n\n")

        for log_path in log_files:
            output.write(f"--- {log_path.name} ---\n")
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    file_lines = f.readlines()[-limit:]
                    if level:
                        level_upper = level.upper()
                        file_lines = [ln for ln in file_lines if level_upper in ln]
                    output.writelines(file_lines)
            except Exception as e:
                output.write(f"[Failed to read: {e}]\n")
            output.write("\n")

        output.seek(0)
        filename = f"system_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        return Response(
            output.getvalue(),
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/plain; charset=utf-8',
            },
        )
    except Exception as e:
        log_with_request_id(f"log export error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "EXPORT_ERROR",
            "message": f"Log export failed: {str(e)}",
            "request_id": rid,
        }), 500


# ============================================================
#  GET /api/backup - DB バックアップ
# ============================================================
@api_bp.route('/backup', methods=['GET'])
@trace_request
def backup_database():
    """データベースのバックアップを作成しダウンロード"""
    rid = get_request_id()
    try:
        db_path = Path(Config.DATA_DIR) / "temperature.db"
        if not db_path.exists():
            return jsonify({
                "status": "error",
                "error_code": "FILE_NOT_FOUND",
                "message": "Database file not found",
                "request_id": rid,
            }), 404

        backup_filename = f"temperature_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_path = Path(Config.DATA_DIR) / backup_filename
        shutil.copy2(db_path, backup_path)

        with open(backup_path, 'rb') as f:
            backup_data = f.read()

        return Response(
            backup_data,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{backup_filename}"',
                'Content-Type': 'application/octet-stream',
            },
        )
    except Exception as e:
        log_with_request_id(f"backup error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "BACKUP_ERROR",
            "message": f"Backup failed: {str(e)}",
            "request_id": rid,
        }), 500


# ============================================================
#  ESP-NOW Master 情報 (2026-08-15 追加)
#  子機スケッチ書込み時に MAC を copy-paste するためのエンドポイント
# ============================================================

@api_bp.route('/masters', methods=['GET'])
@trace_request
def list_masters():
    """
    登録済みの ESP-NOW Master 一覧を取得。
    レスポンス例:
      {
        "status": "success",
        "masters": [
          {
            "device_id": "MST-4D99BC",
            "mac": "2C:BC:BB:4D:99:BC",
            "firmware": "ESP32_ESPNOW_Master 2026-08-15",
            "first_seen": "2026-08-15 06:21:29",
            "last_seen":  "2026-08-15 06:35:41",
            "nickname":   "1F 冷却塔集約器"
          }
        ]
      }
    """
    rid = get_request_id()
    try:
        items = MasterQueries.get_all()
        return jsonify({
            "status": "success",
            "masters": items,
            "count": len(items),
            "request_id": rid,
        })
    except Exception as e:
        log_with_request_id(f"master fetch error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "MASTER_ERROR",
            "message": str(e),
            "request_id": rid,
        }), 500


# ============================================================
#  デバイス表示名 (nickname) 管理 (2026-07-17 追加)
# ============================================================

@api_bp.route('/nicknames', methods=['GET'])
@trace_request
def list_nicknames():
    """全 nickname マッピングを取得"""
    rid = get_request_id()
    try:
        items = NicknameQueries.get_all()
        return jsonify({
            "status": "success",
            "nicknames": items,
            "count": len(items),
            "request_id": rid,
        })
    except Exception as e:
        log_with_request_id(f"nickname fetch error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "NICKNAME_ERROR",
            "message": str(e),
            "request_id": rid,
        }), 500


@api_bp.route('/nicknames/<sensor_id>', methods=['PUT'])
@trace_request
def set_nickname(sensor_id):
    """
    指定 sensor_id に nickname を設定 (upsert)。
    Body: {"nickname": "冷却塔1"}
    """
    rid = get_request_id()
    try:
        data = request.get_json(force=True, silent=True) or {}
        nickname = data.get('nickname')
        if not nickname:
            return jsonify({
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "nickname is required in body",
                "request_id": rid,
            }), 400

        # URL エンコードされている可能性
        sensor_id_decoded = urllib.parse.unquote(sensor_id)

        NicknameQueries.upsert(sensor_id_decoded, nickname.strip())
        log_with_request_id(f"nickname set: {sensor_id_decoded} -> {nickname}")

        return jsonify({
            "status": "success",
            "sensor_id": sensor_id_decoded,
            "nickname": nickname,
            "request_id": rid,
        })
    except ValueError as ve:
        return jsonify({
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": str(ve),
            "request_id": rid,
        }), 400
    except Exception as e:
        log_with_request_id(f"nickname set error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "NICKNAME_ERROR",
            "message": str(e),
            "request_id": rid,
        }), 500


@api_bp.route('/nicknames/<sensor_id>', methods=['DELETE'])
@trace_request
def delete_nickname(sensor_id):
    """指定 sensor_id の nickname を削除"""
    rid = get_request_id()
    try:
        sensor_id_decoded = urllib.parse.unquote(sensor_id)
        deleted = NicknameQueries.delete(sensor_id_decoded)
        log_with_request_id(f"nickname deleted: {sensor_id_decoded} ({deleted} rows)")
        return jsonify({
            "status": "success",
            "sensor_id": sensor_id_decoded,
            "deleted": deleted,
            "request_id": rid,
        })
    except Exception as e:
        log_with_request_id(f"nickname delete error: {e}", 'error')
        return jsonify({
            "status": "error",
            "error_code": "NICKNAME_ERROR",
            "message": str(e),
            "request_id": rid,
        }), 500
