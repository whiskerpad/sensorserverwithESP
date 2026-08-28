"""HTTP エンドポイント。

ルート設計:
    POST /api/temperature                   - ESP (静的IP版) からの受信 (認証なし) ★方針A で追加
    POST /api/sensor                        - ESP (STEP2版) からの受信 (認証なし・レガシー)
    GET  /health                            - ヘルスチェック (認証なし)
    GET  /                                  - ダッシュボード HTML (認証あり)
    GET  /sensor/<device_id>                - デバイス詳細 HTML (認証あり)
    GET  /api/sensors                       - 全デバイス最新値 JSON
    GET  /api/sensor/<device_id>/readings   - 時間範囲データ JSON
    GET  /api/export/<device_id>            - CSV ダウンロード
"""
import csv
import io
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, render_template, Response

from . import database as db
from .auth import basic_auth_required

logger = logging.getLogger(__name__)
bp = Blueprint('main', __name__)


# ---------- 認証なしエンドポイント ----------

@bp.route('/health', methods=['GET'])
def health():
    """ヘルスチェック。監視ツール用。"""
    try:
        record_count = db.count_all()
        return jsonify(
            status='ok',
            time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            record_count=record_count,
        )
    except Exception as e:
        logger.exception("Health check failed")
        return jsonify(status='error', message=str(e)), 500


@bp.route('/api/sensor', methods=['POST'])
def receive_sensor_data():
    """ESP8266 からの温度データを受信 (STEP 2 DHCP 版・レガシー)。

    期待する JSON (STEP 2 スケッチと整合):
        {
          "device_id": "esp8266-01",
          "voltage": 3.31,
          "battery_percent": 78.5,
          "is_battery_mode": false,
          "rssi_dbm": -65,
          "sensors": [
            {"index": 0, "address": "28FFA1B2C3D4E5F6", "temp_c": 24.50},
            {"index": 1, "address": "28AA0123456789AB", "temp_c": null}
          ]
        }

    sensors[] を展開して 1 リクエスト = 複数レコード挿入。
    temp_c: null は「欠測」として保存 (STEP 2 の 85℃再変換失敗時のケース)。
    """
    raw_body = request.get_data(as_text=True)
    logger.info("[POST /api/sensor] from %s: %s",
                request.remote_addr, raw_body[:500])

    data = request.get_json(silent=True)
    if not data:
        logger.warning("Invalid JSON from %s", request.remote_addr)
        return jsonify(status='error', message='Invalid JSON'), 400

    device_id = data.get('device_id')
    if not device_id:
        return jsonify(status='error', message='device_id required'), 400

    sensors = data.get('sensors', [])
    if not isinstance(sensors, list) or len(sensors) == 0:
        return jsonify(status='error', message='sensors[] required'), 400

    voltage = data.get('voltage')
    battery_pct = data.get('battery_percent')
    is_battery = bool(data.get('is_battery_mode', False))
    rssi_dbm = data.get('rssi_dbm')

    saved_count = 0
    received_at = None
    for s in sensors:
        if not isinstance(s, dict):
            continue
        try:
            received_at = db.insert_reading(
                device_id=device_id,
                sensor_index=s.get('index'),
                sensor_addr=s.get('address'),
                temp_c=s.get('temp_c'),
                voltage=voltage,
                battery_pct=battery_pct,
                is_battery=is_battery,
                rssi_dbm=rssi_dbm,
            )
            saved_count += 1
        except Exception as e:
            logger.exception(
                "Failed to insert reading (device=%s, sensor=%s): %s",
                device_id, s.get('index'), e,
            )

    logger.info(
        "[POST /api/sensor] %s: %d/%d sensors saved at %s",
        device_id, saved_count, len(sensors), received_at,
    )
    return jsonify(status='ok', saved=saved_count, received_at=received_at)


@bp.route('/api/temperature', methods=['POST'])
def receive_temperature_data():
    """ESP8266 静的IP版スケッチ (方針 A の主流) からの温度データを受信。

    期待する JSON (フラット構造、1 リクエスト = 1 センサー):
        {
          "device_id": "ESP8266_ip208_30sec",
          "name": "DS18B20-ESP8266-208",
          "temperature": 24.50,
          "temp": 24.50,
          "ip_address": "192.168.4.208",
          "voltage": 3.31,
          "battery_percent": 78,
          "battery_mode": 1,
          "signal_strength": -65
        }

    /api/sensor との差分:
      - フラット構造 (sensors[] 配列ではなく単一センサー)
      - `temperature` (または `temp`) を temp_c に、`signal_strength` を rssi_dbm に、
        `battery_mode` (int) を is_battery (bool) にマップ
      - name / ip_address は新設列に格納
      - sensor_index は常に 0 (チップあたり 1 センサー前提)
    """
    raw_body = request.get_data(as_text=True)
    logger.info("[POST /api/temperature] from %s: %s",
                request.remote_addr, raw_body[:500])

    data = request.get_json(silent=True)
    if not data:
        logger.warning("Invalid JSON from %s", request.remote_addr)
        return jsonify(status='error', message='Invalid JSON'), 400

    device_id = data.get('device_id')
    if not device_id:
        return jsonify(status='error', message='device_id required'), 400

    temp_c = data.get('temperature')
    if temp_c is None:
        temp_c = data.get('temp')
    if temp_c is None:
        return jsonify(status='error', message='temperature (or temp) required'), 400

    try:
        temp_c = float(temp_c)
    except (TypeError, ValueError):
        return jsonify(status='error', message='temperature must be a number'), 400

    voltage = data.get('voltage')
    battery_pct = data.get('battery_percent')
    battery_mode_raw = data.get('battery_mode', 0)
    is_battery = bool(battery_mode_raw) if battery_mode_raw is not None else False
    rssi_dbm = data.get('signal_strength')
    name = data.get('name')
    ip_address = data.get('ip_address')

    try:
        received_at = db.insert_reading(
            device_id=device_id,
            sensor_index=0,
            sensor_addr=None,
            temp_c=temp_c,
            voltage=voltage,
            battery_pct=battery_pct,
            is_battery=is_battery,
            rssi_dbm=rssi_dbm,
            name=name,
            ip_address=ip_address,
        )
    except Exception as e:
        logger.exception("Failed to insert reading (device=%s): %s", device_id, e)
        return jsonify(status='error', message='DB insert failed'), 500

    logger.info("[POST /api/temperature] %s (%s): temp=%s saved at %s",
                device_id, name, temp_c, received_at)
    return jsonify(status='ok', saved=1, received_at=received_at)


# ---------- 認証ありエンドポイント (JSON API) ----------

@bp.route('/api/sensors', methods=['GET'])
@basic_auth_required
def api_sensors():
    """全デバイスの最新値。"""
    return jsonify(sensors=db.get_all_devices_latest())


@bp.route('/api/sensor/<device_id>/readings', methods=['GET'])
@basic_auth_required
def api_sensor_readings(device_id):
    """指定デバイスの時間範囲データ + 統計。"""
    try:
        hours = float(request.args.get('hours', 24))
    except ValueError:
        return jsonify(status='error', message='hours must be a number'), 400

    readings = db.get_readings(device_id, hours=hours)
    stats = db.get_stats(device_id, hours=hours)
    return jsonify(
        device_id=device_id,
        hours=hours,
        readings=readings,
        stats=stats,
        count=len(readings),
    )


@bp.route('/api/export/<device_id>', methods=['GET'])
@basic_auth_required
def api_export(device_id):
    """指定デバイスのデータを CSV でダウンロード。"""
    try:
        hours = float(request.args.get('hours', 24))
    except ValueError:
        return Response('hours must be a number', 400)

    readings = db.get_readings(device_id, hours=hours)

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        'received_at', 'name', 'ip_address', 'sensor_index', 'sensor_addr',
        'temp_c', 'voltage', 'battery_pct', 'is_battery', 'rssi_dbm',
    ])
    for r in readings:
        writer.writerow([
            r['received_at'],
            r.get('name'), r.get('ip_address'),
            r['sensor_index'], r['sensor_addr'], r['temp_c'],
            r['voltage'], r['battery_pct'], r['is_battery'], r['rssi_dbm'],
        ])

    filename = f"{device_id}_last{int(hours)}h.csv"
    return Response(
        out.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


# ---------- 認証ありエンドポイント (HTML) ----------

@bp.route('/', methods=['GET'])
@basic_auth_required
def index():
    """ダッシュボード。全デバイスの最新値を一覧表示。"""
    latest = db.get_all_devices_latest()
    devices = {}
    for r in latest:
        did = r['device_id']
        if did not in devices:
            devices[did] = {'device_id': did, 'sensors': []}
        devices[did]['sensors'].append(r)
    return render_template('index.html', devices=list(devices.values()))


@bp.route('/sensor/<device_id>', methods=['GET'])
@basic_auth_required
def sensor_detail(device_id):
    """デバイス詳細ページ。Chart.js でトレンドを描画。"""
    return render_template('sensor.html', device_id=device_id)
