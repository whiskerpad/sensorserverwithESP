# ESP-NOW 実装 - マスター ESP32 + センサー ESP8266

## デバイス情報

| 役割 | デバイス | MAC アドレス |
|-----|--------|------------|
| **マスター** | ESP32 | `2C:BC:BB:4D:99:BC` |
| **センサー** | ESP8266 | `5C:CF:7F:08:32:C0` |

---

## 1. マスター ESP32 コード

ラズパイの USB に接続し、複数のセンサーから ESP-NOW でデータを受信してシリアル送信します。

### Arduino IDE での設定
- ボード: ESP32 Dev Module
- ボーレート: 115200
- Flash Mode: DIO

### スケッチ

```cpp
#include <esp_now.h>
#include <WiFi.h>
#include <ArduinoJson.h>

#define MASTER_DEVICE_ID "ESP32_MAIN"
#define BAUD_RATE 115200

// ESP-NOWで受信したセンサーデータ構造
typedef struct {
    char sensor_id[16];      // "ESP8266_PROT_01"など
    char sensor_name[32];    // "DHT22-01"など
    float temp;              // 温度(℃)
    float humidity;          // 湿度(%)
    int8_t rssi;             // 信号強度(dBm)
    uint32_t timestamp;      // タイムスタンプ
} SensorData;

// グローバル変数
SensorData received_data[10];  // 最大10個のセンサーデータ
int data_count = 0;
unsigned long last_send_time = 0;

// ESP-NOW受信コールバック
void on_data_recv(const uint8_t *mac_addr, const uint8_t *incomingData, int len) {
    if (data_count < 10) {
        memcpy(&received_data[data_count], incomingData, sizeof(SensorData));
        data_count++;
        Serial.printf("[ESP-NOW] Received from %02X:%02X:%02X:%02X:%02X:%02X\n",
            mac_addr[0], mac_addr[1], mac_addr[2], 
            mac_addr[3], mac_addr[4], mac_addr[5]);
    }
}

void setup() {
    Serial.begin(BAUD_RATE);
    delay(1000);
    
    Serial.println("\n\n=== ESP32 Master (ESP-NOW) ===");
    Serial.println("Device ID: " + String(MASTER_DEVICE_ID));
    Serial.printf("MAC Address: %02X:%02X:%02X:%02X:%02X:%02X\n",
        WiFi.macAddress()[0], WiFi.macAddress()[1], WiFi.macAddress()[2],
        WiFi.macAddress()[3], WiFi.macAddress()[4], WiFi.macAddress()[5]);
    
    // WiFi初期化（ESP-NOWに必須）
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
    
    // ESP-NOW初期化
    if (esp_now_init() != ESP_OK) {
        Serial.println("ERROR: ESP-NOW initialization failed");
        return;
    }
    
    // コールバック登録
    esp_now_register_recv_cb(on_data_recv);
    
    Serial.println("Status: Ready to receive ESP-NOW data");
    Serial.println("Waiting for sensor data...\n");
}

void loop() {
    // 1秒ごとにラズパイへデータ送信
    unsigned long current_time = millis();
    
    if (current_time - last_send_time >= 1000) {
        if (data_count > 0) {
            send_to_raspberry();
            data_count = 0;  // バッファをリセット
        }
        last_send_time = current_time;
    }
    
    delay(10);
}

void send_to_raspberry() {
    // JSONドキュメントを作成
    StaticJsonDocument<512> doc;
    doc["device_id"] = MASTER_DEVICE_ID;
    doc["timestamp"] = millis();
    
    // センサーデータ配列を作成
    JsonArray sensors = doc.createNestedArray("sensors");
    
    for (int i = 0; i < data_count; i++) {
        JsonObject sensor = sensors.createNestedObject();
        sensor["sensor_id"] = received_data[i].sensor_id;
        sensor["sensor_name"] = received_data[i].sensor_name;
        sensor["temperature"] = received_data[i].temp;
        sensor["humidity"] = received_data[i].humidity;
        sensor["rssi"] = received_data[i].rssi;
    }
    
    // シリアル出力（JSON形式）
    serializeJson(doc, Serial);
    Serial.println();  // 改行で1行を終了
}
```

---

## 2. センサー ESP8266 コード

DHT22 センサーを接続し、温度・湿度データを ESP-NOW でマスター ESP32 に送信します。

### ハードウェア接続
```
DHT22 ピン配置:
1 (VCC)   → ESP8266 3.3V
2 (DATA)  → ESP8266 D4 (GPIO2)
3 (GND)   → ESP8266 GND
4 (-)     → 接続なし

プルアップ抵抗: 4.7kΩ (DATA と VCC 間)
```

### Arduino IDE での設定
- ボード: NodeMCU 1.0 (ESP8266-12E)
- ボーレート: 115200

### ライブラリインストール
Arduino IDE → スケッチ → ライブラリをインクルード → ライブラリマネージャー
- "DHT" で検索 → "DHT sensor library" by Adafruit をインストール
- "Adafruit Unified Sensor" もインストール

### スケッチ

```cpp
#include <esp_now.h>
#include <ESP8266WiFi.h>
#include "DHT.h"

// ===== 設定 =====
#define DHTPIN D4              // DHT22 データピン (GPIO2)
#define DHTTYPE DHT22          // DHT22 センサー
#define SENSOR_ID "ESP8266_PROT_01"
#define SENSOR_NAME "DHT22-01"
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

DHT dht(DHTPIN, DHTTYPE);
unsigned long last_send_time = 0;

// ESP-NOW送信コールバック
void on_data_sent(uint8_t *mac_addr, uint8_t status) {
    Serial.print("Send Status: ");
    Serial.println(status == 0 ? "Success" : "Failed");
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n=== ESP8266 Sensor (ESP-NOW) ===");
    Serial.println("Sensor ID: " + String(SENSOR_ID));
    Serial.println("Sensor Name: " + String(SENSOR_NAME));
    
    // DHT初期化
    dht.begin();
    Serial.println("DHT22 initialized");
    
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
    // DHT22からセンサーデータを読み込み
    float humidity = dht.readHumidity();
    float temp = dht.readTemperature();
    
    // エラーチェック
    if (isnan(humidity) || isnan(temp)) {
        Serial.println("ERROR: Failed to read DHT22");
        return;
    }
    
    // センサーデータ構造体を作成
    SensorData sensor_data;
    strcpy(sensor_data.sensor_id, SENSOR_ID);
    strcpy(sensor_data.sensor_name, SENSOR_NAME);
    sensor_data.temp = temp;
    sensor_data.humidity = humidity;
    sensor_data.rssi = WiFi.RSSI();
    sensor_data.timestamp = millis();
    
    // 送信
    esp_now_send(masterMAC, (uint8_t *)&sensor_data, sizeof(sensor_data));
    
    // ログ出力
    Serial.print("Sent: Temp=");
    Serial.print(temp);
    Serial.print("°C, Humidity=");
    Serial.print(humidity);
    Serial.println("%");
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
=== ESP8266 Sensor (ESP-NOW) ===
Sensor ID: ESP8266_PROT_01
Sensor Name: DHT22-01
DHT22 initialized
ESP8266 MAC: 5C:CF:7F:08:32:C0
Master registered
Status: Ready to send sensor data

Sent: Temp=22.5°C, Humidity=45.2%
Sent: Temp=22.5°C, Humidity=45.2%
```

### ラズパイのログ

```bash
tail -f /home/pi/temperature_server/logs/app.routes.api.log
```

JSON データが 30秒ごとに受信・保存されます。

---

## トラブルシューティング

### ESP-NOW が接続されない

**マスター側:**
```
ERROR: ESP-NOW initialization failed
```

**センサー側:**
```
ERROR: ESP-NOW initialization failed
```

**解決方法:**
- WiFi.disconnect() が正しく実行されているか確認
- ボードの電源をリセット（USB 再接続）
- Arduino IDE の "Tools" → "Erase All Flash Before Sketch Upload" をチェックして書き込み

### センサーデータが受信されない

**原因:**
- MAC アドレスが正しく設定されていない
- 距離が遠すぎる（ESP-NOW は 100m 以上離れると不安定）
- 他の 2.4GHz 無線機器の干渉

**確認方法:**
```
シリアルモニターで "[ESP-NOW] Received from..." メッセージが表示されているか確認
```

### ラズパイにデータが届かない

**ログ確認:**
```bash
tail -50 /home/pi/temperature_server/logs/main.log
tail -50 /home/pi/temperature_server/logs/app.routes.api.log
```

---

## 複数センサーの追加

さらに ESP32 センサーを追加する場合：

1. MAC アドレスを取得
2. 新しい ESP8266/ESP32 に同じセンサーコードを書き込み
3. `SENSOR_ID` と `SENSOR_NAME` を変更（例: `ESP32_PROT_02`, `DHT22-02`）
4. マスターのコードは変更不要（自動で複数センサーに対応）
