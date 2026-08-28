"""
temperature_server/services/serial_reader.py
USB/シリアル経由でESP32からの温度データを受信

システム構成:
- ラズパイにUSB接続されたESP32がマスター
- このESP32はESP-NOWで複数のESP32/ESP8266からデータを受信
- ラズパイはUSB/シリアル経由でこのESP32から温度データを取得
- 受信データをSQLiteに格納
"""

import serial
import threading
import json
import logging
import time
from config import Config
from database.queries import TemperatureQueries, NicknameQueries, MasterQueries

logger = logging.getLogger(__name__)


class SerialReader:
    """USB/シリアル経由でESP32からデータを受信"""
    
    def __init__(self, port=None, baudrate=115200, timeout=1):
        """
        初期化
        
        Args:
            port (str): シリアルポート（例: '/dev/ttyUSB0'）
                       Noneの場合は自動検出
            baudrate (int): ボーレート（デフォルト: 115200）
            timeout (float): 読み込みタイムアウト（秒）
        """
        self.port = port or self._auto_detect_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.is_running = False
        self.reader_thread = None
        
        logger.info(f"SerialReader initialized: port={self.port}, baudrate={self.baudrate}")
    
    def _auto_detect_port(self):
        """
        利用可能なシリアルポートを自動検出
        
        /dev/ttyUSB* または /dev/ttyACM* から検出
        複数ある場合は最初のものを使用
        
        Returns:
            str: ポートパス（見つからない場合はNone）
        """
        try:
            import glob
            # Linux: /dev/ttyUSB* (CH340等) または /dev/ttyACM* (STM32等)
            ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
            if ports:
                detected_port = ports[0]
                logger.info(f"Auto-detected serial port: {detected_port}")
                return detected_port
            
            logger.warning("No serial port found. Please check USB connection.")
            return None
        except Exception as e:
            logger.error(f"Error auto-detecting serial port: {e}")
            return None
    
    def connect(self):
        """
        シリアルポートを開く
        
        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            if not self.port:
                logger.error("Serial port not specified and auto-detection failed")
                return False
            
            # シリアルポートを開く
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            
            logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        
        except serial.SerialException as e:
            logger.error(f"Failed to connect to serial port: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during serial connection: {e}")
            return False
    
    def disconnect(self):
        """シリアルポートを閉じる"""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                logger.info("Disconnected from serial port")
        except Exception as e:
            logger.error(f"Error closing serial port: {e}")
    
    # 2026-08-19 追加: 再接続リトライ間隔
    RECONNECT_INTERVAL_SEC = 30

    def start(self):
        """
        シリアル受信スレッドを開始 (2026-08-19 修正: 自動再接続対応)

        起動時に Master が未接続でもスレッドは起動し、read_loop 内で
        RECONNECT_INTERVAL_SEC ごとに connect() を再試行する。
        途中で USB が抜けた場合も同じロジックで自動復旧する。
        """
        if self.is_running:
            logger.warning("Serial reader is already running")
            return

        # 起動時 connect は失敗しても続行 (read_loop がリトライを担う)
        connected = self.connect()
        if not connected:
            logger.warning(
                f"Initial serial connect failed, will retry every "
                f"{self.RECONNECT_INTERVAL_SEC}s in background thread"
            )

        self.is_running = True
        self.reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.reader_thread.start()
        logger.info("Serial reader thread started (with auto-reconnect)")

    def stop(self):
        """シリアル受信スレッドを停止"""
        self.is_running = False
        if self.reader_thread:
            self.reader_thread.join(timeout=5)
        self.disconnect()
        logger.info("Serial reader stopped")

    def _ensure_connected(self):
        """
        接続を確認、切れていれば再接続を試みる (2026-08-19 追加)
        戻り値: True=接続 OK、False=接続不能 (次回リトライ)
        """
        if self.serial_conn and self.serial_conn.is_open:
            return True
        # ポートパスも auto-detect し直す (ttyUSB0/1 が入替わっても追随)
        if not self.port:
            self.port = self._auto_detect_port()
        if not self.port:
            return False
        return self.connect()

    def _read_loop(self):
        """
        シリアル読み込みループ (2026-08-19 修正: 自動再接続内蔵)

        USB が抜けたり Master が停止すると SerialException が飛ぶので、
        catch して disconnect → RECONNECT_INTERVAL_SEC 待機 → 再接続試行、
        を is_running が False になるまで繰り返す。
        """
        buffer = ""
        last_reconnect_attempt = 0.0

        while self.is_running:
            # ---- 未接続なら再接続を試みる (最初の 30 秒はスリープしない即試行) ----
            if not (self.serial_conn and self.serial_conn.is_open):
                now = time.time()
                if now - last_reconnect_attempt < self.RECONNECT_INTERVAL_SEC:
                    time.sleep(1)
                    continue
                last_reconnect_attempt = now
                logger.info(f"Attempting serial reconnect to {self.port or '(auto-detect)'}...")
                if self._ensure_connected():
                    logger.info(f"Serial reconnected to {self.port}")
                    buffer = ""
                else:
                    logger.debug(f"Serial reconnect failed, will retry in "
                                 f"{self.RECONNECT_INTERVAL_SEC}s")
                    time.sleep(1)
                    continue

            # ---- 通常の読み取りループ ----
            try:
                if self.serial_conn.in_waiting > 0:
                    byte = self.serial_conn.read(1).decode('utf-8', errors='ignore')
                    buffer += byte
                    if byte == '\n':
                        line = buffer.strip()
                        buffer = ""
                        if line:
                            self._process_line(line)
                else:
                    time.sleep(0.01)  # CPU 負荷軽減
            except UnicodeDecodeError:
                buffer = ""
            except (serial.SerialException, OSError) as e:
                # USB 抜き挿し等でポートが死んだ状態
                logger.warning(f"Serial port lost ({e}), disconnecting and will reconnect")
                self.disconnect()
                buffer = ""
                # 次ループ先頭で再接続処理へ
            except Exception as e:
                logger.error(f"Unexpected error in read loop: {e}", exc_info=True)
                time.sleep(1)
    
    def _process_line(self, line):
        """
        受信した1行をパース・処理
        
        フォーマット例:
        {"device_id":"ESP32_MAIN","sensors":[{"sensor_id":"ESP32_PROT_01","temp":22.5,"humidity":45.2},...]}
        
        Args:
            line (str): 受信した行文字列
        """
        try:
            # JSON パース
            data = json.loads(line)
            logger.debug(f"Received JSON: {data}")
            
            # データ処理
            self._process_json_data(data)
        
        except json.JSONDecodeError as e:
            # JSON形式以外のテキスト（デバッグ出力等）はスキップ
            logger.debug(f"Non-JSON line: {line}")
        except Exception as e:
            logger.error(f"Error processing line: {e}")
    
    def _process_json_data(self, data):
        """
        受信したJSONデータを処理・DB保存

        3 種類の JSON を受け取る (2026-08-15 拡張):

        1) master_hello  — Master 起動時 1 回
           {"type":"master_hello","device_id":"MST-A1B2C3","mac":"...","firmware":"..."}

        2) master_status — Master が 60 秒ごとに送出 (heartbeat + Pi 後起動対応)
           {"type":"master_status","device_id":"MST-A1B2C3","mac":"...","uptime_ms":...}

        3) センサーデータ (type フィールドなし、または type=sensor_data)
           {
             "device_id": "MST-A1B2C3",           ← Master 自身の ID (旧 ESP32_MAIN)
             "sensors": [
               {"sensor_id":"NOW-XXX","temp":22.5,"humidity":0,"rssi":-45},
               ...
             ]
           }
        """
        try:
            msg_type = data.get('type', '')

            # ---- Master の自己紹介 / heartbeat ----
            if msg_type in ('master_hello', 'master_status'):
                self._register_master(data)
                return

            # ---- 従来のセンサーデータ配列 ----
            master_device_id = data.get('device_id')
            if not master_device_id:
                logger.warning("Missing 'device_id' in received data")
                return

            sensors = data.get('sensors', [])
            if not isinstance(sensors, list):
                logger.warning(f"Invalid 'sensors' format: {type(sensors)}")
                return

            saved_count = 0
            for sensor in sensors:
                if self._save_sensor_data(sensor, master_device_id):
                    saved_count += 1

            if saved_count > 0:
                logger.info(f"[Serial] Saved {saved_count} sensor readings from {master_device_id}")

        except Exception as e:
            logger.error(f"Error processing JSON data: {e}", exc_info=True)

    def _register_master(self, data):
        """
        master_hello / master_status を受けて Master を DB に自己登録。
        - masters テーブル: device_id / mac / firmware / last_seen 更新 (heartbeat)
        - device_nicknames: 初回のみデフォルト名で仮登録 (ユーザ設定は上書きしない)
        (2026-08-15 追加、08-15 masters テーブル対応で MAC 保持)
        """
        try:
            master_id = data.get('device_id')
            master_mac = data.get('mac', '')
            firmware = data.get('firmware')
            if not master_id:
                logger.warning(f"[Master] missing device_id in {data.get('type')}")
                return
            if not master_mac:
                logger.warning(f"[Master] missing mac in {data.get('type')} for {master_id}")
                # MAC 未指定でも nickname 側だけ登録
            else:
                MasterQueries.upsert(master_id, master_mac, firmware)

            default_name = f"ESP-NOW Master ({master_mac[-8:] if len(master_mac) >= 8 else master_mac or master_id})"
            newly_added = NicknameQueries.register_if_absent(master_id, default_name)
            if newly_added:
                logger.info(f"[Master] Registered new: {master_id} mac={master_mac}")
            else:
                logger.debug(f"[Master] heartbeat: {master_id} mac={master_mac}")
        except Exception as e:
            logger.error(f"[Master] Registration failed: {e}", exc_info=True)
    
    def _save_sensor_data(self, sensor, master_id):
        """
        センサーデータをDBに保存
        
        Args:
            sensor (dict): センサーデータ
            master_id (str): マスターESP32のID
        
        Returns:
            bool: 保存成功時True
        """
        try:
            # 必須フィールド取得
            sensor_id = sensor.get('sensor_id')
            temperature = sensor.get('temp') or sensor.get('temperature')
            
            if not sensor_id or temperature is None:
                logger.warning(f"Missing required fields in sensor data: {sensor}")
                return False
            
            # オプショナルフィールド
            sensor_name = sensor.get('sensor_name', 'Unknown')
            humidity = sensor.get('humidity')
            rssi = sensor.get('rssi')            # Master 側で計測した ESP-NOW 物理層 RSSI
            battery_mode = sensor.get('battery_mode', False)

            # DBに挿入
            # 2026-08-13 修正:
            #   従来は rssi を受け取っておきながら insert_reading に渡していないため
            #   DB の rssi 列が常に NULL → ダッシュボード/LCD の電波強度が出ない
            #   バグだった。rssi と connection_type='esp_now' を明示的に渡す。
            #   (insert_reading の auto 判定は rssi の有無で wifi_ap / esp_now を分岐する
            #   ので、ESP-NOW 経路であることを connection_type で強制指定する)
            TemperatureQueries.insert_reading(
                sensor_id=sensor_id,
                temperature=float(temperature),
                sensor_name=sensor_name,
                humidity=float(humidity) if humidity is not None else None,
                rssi=int(rssi) if rssi is not None else None,
                battery_mode=bool(battery_mode),
                connection_type='esp_now',
            )

            logger.debug(
                f"[Serial] Saved: {sensor_id} = {temperature}°C "
                f"(via {master_id}, name={sensor_name}, humidity={humidity}, rssi={rssi})"
            )
            return True
        
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid data type in sensor: {sensor}, error: {e}")
            return False
        except Exception as e:
            logger.error(f"Error saving sensor data: {e}", exc_info=True)
            return False


def create_serial_reader(config_obj=None):
    """
    SerialReaderのファクトリ関数
    
    Args:
        config_obj: Config オブジェクト（デフォルト: Config）
    
    Returns:
        SerialReader: 初期化済みのSerialReaderインスタンス
    """
    if config_obj is None:
        config_obj = Config
    
    reader = SerialReader(
        port=getattr(config_obj, 'SERIAL_PORT', None),
        baudrate=getattr(config_obj, 'SERIAL_BAUDRATE', 115200),
        timeout=getattr(config_obj, 'SERIAL_TIMEOUT', 1)
    )
    return reader
