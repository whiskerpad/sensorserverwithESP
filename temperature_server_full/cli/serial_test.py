"""
temperature_server/cli/serial_test.py
シリアル通信テストツール

実装されたESP32マスターがシリアル経由で送信するJSONフォーマット:

{
  "device_id": "ESP32_MAIN",
  "sensors": [
    {
      "sensor_id": "ESP32_PROT_01",
      "sensor_name": "DS18B20-01",
      "temp": 22.5,
      "humidity": 45.2,
      "rssi": -45
    },
    {
      "sensor_id": "ESP32_PROT_02",
      "sensor_name": "DS18B20-02",
      "temp": 23.1,
      "humidity": 46.8,
      "rssi": -52
    }
  ]
}

使い方:
1. テスト用マスターESP32がある場合:
   python cli/serial_test.py --listen
   
2. テストJSONを送信する場合:
   python cli/serial_test.py --send /dev/ttyUSB0
   
3. シリアルポート一覧を確認:
   python cli/serial_test.py --list
"""

import sys
import json
import argparse
import serial
from pathlib import Path
import glob
import time

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.serial_reader import create_serial_reader
from config import Config
from logger import setup_logger

logger = setup_logger('serial_test')


def list_serial_ports():
    """利用可能なシリアルポートを列挙"""
    print("📡 Available serial ports:")
    
    ports = glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*') + glob.glob('COM*')
    
    if not ports:
        print("  No serial ports found")
        return
    
    for port in ports:
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            print(f"  ✅ {port} (115200 baud)")
            ser.close()
        except:
            print(f"  ⚠️  {port} (cannot connect)")


def send_test_data(port='/dev/ttyUSB0'):
    """テストデータを送信"""
    print(f"📤 Sending test data to {port}...")
    
    try:
        ser = serial.Serial(port, 115200, timeout=1)
        
        # テスト1: 単一センサー
        test_data_1 = {
            "device_id": "ESP32_MAIN",
            "sensors": [
                {
                    "sensor_id": "ESP32_PROT_01",
                    "sensor_name": "DS18B20-01",
                    "temp": 22.5,
                    "humidity": 45.2,
                    "rssi": -45
                }
            ]
        }
        
        print(f"  Test 1: Single sensor")
        json_line = json.dumps(test_data_1) + "\n"
        ser.write(json_line.encode())
        print(f"    Sent: {json_line.strip()}")
        time.sleep(1)
        
        # テスト2: 複数センサー
        test_data_2 = {
            "device_id": "ESP32_MAIN",
            "sensors": [
                {
                    "sensor_id": "ESP32_PROT_01",
                    "sensor_name": "DS18B20-01",
                    "temp": 22.1,
                    "humidity": 45.5,
                    "rssi": -44
                },
                {
                    "sensor_id": "ESP32_PROT_02",
                    "sensor_name": "DS18B20-02",
                    "temp": 23.2,
                    "humidity": 47.1,
                    "rssi": -51
                },
                {
                    "sensor_id": "ESP8266_PROT_03",
                    "sensor_name": "DHT22-03",
                    "temp": 21.8,
                    "humidity": 48.3,
                    "rssi": -58
                }
            ]
        }
        
        print(f"  Test 2: Multiple sensors (ESP32 + ESP8266)")
        json_line = json.dumps(test_data_2) + "\n"
        ser.write(json_line.encode())
        print(f"    Sent: {json_line.strip()}")
        
        print("✅ Test data sent successfully")
        ser.close()
    
    except Exception as e:
        print(f"❌ Error: {e}")


def listen_serial(port=None):
    """シリアルデータをリッスン"""
    print("📡 Listening to serial port...")
    
    reader = create_serial_reader(Config)
    if reader.port is None:
        print("❌ No serial port found")
        return
    
    print(f"Connected to: {reader.port}")
    print(f"Baudrate: {reader.baudrate}")
    print("Press Ctrl+C to exit\n")
    
    reader.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        reader.stop()
        print("✅ Stopped")


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='Serial communication test tool for ESP32/Temperature Server'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available serial ports'
    )
    
    parser.add_argument(
        '--listen',
        action='store_true',
        help='Listen to serial data (auto-detect port)'
    )
    
    parser.add_argument(
        '--send',
        type=str,
        nargs='?',
        const='/dev/ttyUSB0',
        help='Send test data to serial port (default: /dev/ttyUSB0)'
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_serial_ports()
    elif args.listen:
        listen_serial()
    elif args.send:
        send_test_data(args.send)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
