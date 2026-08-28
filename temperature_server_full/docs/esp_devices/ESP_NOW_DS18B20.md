# ESP-NOW 実装 - マスター ESP32 + センサー ESP8266（DS18B20）

## デバイス情報

| 役割 | デバイス | MAC アドレス |
|-----|--------|------------|
| **マスター** | ESP32 | `2C:BC:BB:4D:99:BC` |
| **センサー** | ESP8266 | `5C:CF:7F:08:32:C0` |

---

## 1. マスター ESP32 コード（変更なし）

[前のドキュメントと同じコード](ESP_NOW_IMPLEMENTATION.md#1-マスター-esp32-コード)を使用してください。

---

## 2. センサー ESP8266 コード（DS18B20 版）

DS18B20 温度センサーを接続し、温度データを ESP-NOW でマスター ESP32 に送信します。

### ハードウェア接続

```
DS18B20 配線（パラサイト電源モード）:

DS18B20 ピン配置（背面から見た場合、左から）:
┌─────────┬─────────┬─────────┐
│   GND   │  DATA   │  VCC    │
│  (黒)    │ (黄)     │  (赤)    │
└─────────┴─────────┴─────────┘

ESP8266 接続:
GND (黒)   → ESP8266 GND
DATA (黄)  → ESP8266 D4 (GPIO2)
VCC (赤)   → ESP8266 3.3V

プルアップ抵抗: 4.7kΩ を DATA と VCC 間に接続
```

### Arduino IDE での設定
- ボード: NodeMCU 1.0 (ESP8266-12E)
- ボーレート: 115200

### ライブラリインストール
Arduino IDE → スケッチ → ライブラリをインクルード → ライブラリマネージャー
- "OneWire" by Jim Studt, Paul Stoffregen をインストール
- "DallasTemperature" by Miles Burton をインストール

### スケッチ

```cpp
#include <esp_now.h>
#include <ESP8266WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ===== 設定 =====
#define ONE_WIRE_BUS D4        // DS18B20 データピン (GPIO2)
#define SENSOR_ID "ESP8266_PROT_01"
#define SENSOR_NAME "DS18B20-01"
#define SEND_INTERVAL 30000    // 30秒ごとに送信

// マスター ESP32 の MAC アドレス
uint8_t masterMAC[] = {0x2C, 0xBC, 0xBB, 0x4D, 0x99, 0xBC};

// センサーデータ構造（マスターと同じ）
typedef struct {
    char sensor_id[16];
    char sensor_name[32];
    float temp;
    float humidity;
    int8_t rssi;
    uint32_t timestamp;
} SensorData;

// OneWire と DallasTemperature インスタンス
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

unsigned long last_send_time = 0;

// ESP-NOW送信コールバック
void on_data_sent(uint8_t *mac_addr, uint8_t status) {
    Serial.print("Send Status: ");
    Serial.println(status == 0 ? "Success" : "Failed");
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n=== ESP8266 Sensor with DS18B20 (ESP-NOW) ===");
    Serial.println("Sensor ID: " + String(SENSOR_ID));
    Serial.println("Sensor Name: " + String(SENSOR_NAME));
    
    // DS18B20初期化
    sensors.begin();
    int deviceCount = sensors.getDeviceCount();
    Serial.print("DS18B20 Found: ");
    Serial.println(deviceCount);
    
    if (deviceCount == 0) {
        Serial.println("ERROR: No DS18B20 sensor found!");
        Serial.println("Check wiring and power supply");
    }
    
    // WiFi初期化（ESP-NOWに必須）
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
    
    Serial.printf("ESP8266 MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
        WiFi.macAddress()[0], WiFi.macAddress()[1], WiFi.macAddress()[2],
        WiFi.macAddress()[3], WiFi.macAddress()[4], WiFi.macAddress()[5]);
    
    // ESP-NOW初期化
    if (esp_now_init() != 0) {
        Serial.println("ERROR: ESP-NOW initialization failed");
        return;
    }
    
    // マスターとして登録
    esp_now_set_self_role(ESP_NOW_ROLE_CONTROLLER);
    esp_now_register_send_cb(on_data_sent);
    
    // ピア登録（マスター ESP32）
    esp_now_add_peer(masterMAC, ESP_NOW_ROLE_SLAVE, 1, NULL, 0);
    
    Serial.println("Master registered");
    Serial.println("Status: Ready to send sensor data\n");
}

void loop() {
    unsigned long current_time = millis();
    
    // SEND_INTERVAL ごとにセンサーデータを送信
    if (current_time - last_send_time >= SEND_INTERVAL) {
        send_sensor_data();
        last_send_time = current_time;
    }
    
    delay(100);
}

void send_sensor_data() {
    // DS18B20 から温度を読み込み
    sensors.requestTemperatures();
    delay(100);  // 変換完了待機
    
    // 最初のセンサーの温度を取得
    float temp = sensors.getTempCByIndex(0);
    
    // エラーチェック
    if (temp == DEVICE_DISCONNECTED_C) {
        Serial.println("ERROR: DS18B20 disconnected or not responding");
        return;
    }
    
    // センサーデータ構造体を作成
    SensorData sensor_data;
    strcpy(sensor_data.sensor_id, SENSOR_ID);
    strcpy(sensor_data.sensor_name, SENSOR_NAME);
    sensor_data.temp = temp;
    sensor_data.humidity = 0.0;  // DS18B20 は湿度を測定しないので 0
    sensor_data.rssi = WiFi.RSSI();
    sensor_data.timestamp = millis();
    
    // 送信
    esp_now_send(masterMAC, (uint8_t *)&sensor_data, sizeof(sensor_data));
    
    // ログ出力
    Serial.print("Sent: Temp=");
    Serial.print(temp);
    Serial.println("°C");
}
```

---

## 3. ラズパイ側の設定

### .env ファイル設定

```bash
# シリアル通信設定
SERIAL_ENABLED=True
SERIAL_PORT=/dev/ttyUSB0
SERIAL_BAUDRATE=115200
SERIAL_TIMEOUT=1.0
```

### サーバー起動

```bash
cd /home/pi/temperature_server
source venv/bin/activate
python run.py
```

---

## 動作確認

### Arduino IDE シリアルモニター（マスター ESP32）

```
=== ESP32 Master (ESP-NOW) ===
Device ID: ESP32_MAIN
MAC Address: 2C:BC:BB:4D:99:BC
Status: Ready to receive ESP-NOW data
Waiting for sensor data...

[ESP-NOW] Received from 5C:CF:7F:08:32:C0
```

### Arduino IDE シリアルモニター（センサー ESP8266）

```
=== ESP8266 Sensor with DS18B20 (ESP-NOW) ===
Sensor ID: ESP8266_PROT_01
Sensor Name: DS18B20-01
DS18B20 Found: 1
ESP8266 MAC: 5C:CF:7F:08:32:C0
Master registered
Status: Ready to send sensor data

Sent: Temp=22.5°C
Sent: Temp=22.5°C
```

### ラズパイのログ

```bash
tail -f /home/pi/temperature_server/logs/app.routes.api.log
```

JSON データが 30秒ごとに受信・保存されます。

---

## DS18B20 トラブルシューティング

### DS18B20 が検出されない

```
ERROR: No DS18B20 sensor found!
Check wiring and power supply
```

**確認方法:**
1. **配線確認**: GND、DATA、VCC が正しく接続されているか
2. **プルアップ抵抗**: 4.7kΩ が DATA と VCC 間に接続されているか
3. **電源**: ESP8266 に電源が供給されているか
4. **アドレス確認**: 以下のスケッチで DS18B20 を検出

```cpp
#include <OneWire.h>
#include <DallasTemperature.h>

#define ONE_WIRE_BUS D4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);
  sensors.begin();
  Serial.print("Devices: ");
  Serial.println(sensors.getDeviceCount());
}

void loop() {}
```

### 温度値が不安定

**原因:**
- 接触不良
- ノイズ干渉
- 電源供給不足

**解決方法:**
- プルアップ抵抗を確認（4.7kΩ推奨）
- 配線を再確認
- 別の D ピンを試す（例: D3 = GPIO0）

---

## 複数の DS18B20 センサー接続

DS18B20 は 1-Wire バスを使用しているため、複数を並列接続できます：

```cpp
// 複数の DS18B20 を接続した場合
for (int i = 0; i < sensors.getDeviceCount(); i++) {
    float temp = sensors.getTempCByIndex(i);
    Serial.print("Sensor ");
    Serial.print(i);
    Serial.print(": ");
    Serial.println(temp);
}
```

---

## ESP-NOW が接続されない場合

**マスター側:**
```
ERROR: ESP-NOW initialization failed
```

**解決方法:**
- WiFi.disconnect() が正しく実行されているか確認
- ボードの電源をリセット（USB 再接続）
- Arduino IDE の "Tools" → "Erase All Flash Before Sketch Upload" をチェック

---

## 次のステップ

1. マスター ESP32 にマスターコードを書き込み
2. センサー ESP8266 にこのコードを書き込み
3. DS18B20 をセンサー ESP8266 に接続
4. マスター ESP32 をラズパイに USB 接続
5. ラズパイで `python run.py` を実行

データが正常に受信・保存されることを確認してください！
