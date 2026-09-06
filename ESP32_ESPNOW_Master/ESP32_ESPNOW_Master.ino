/**
 * ============================================================
 *  ESP32 Master (ESP-NOW 受信 + Serial 出力)
 *
 *  役割: 各 ESP-NOW センサーからのデータを受信し、
 *        Serial (USB CDC) 経由で Raspberry Pi に JSON で転送する
 *
 *  ラズパイ側は services/serial_reader.py が Serial 出力を読取り、
 *  /api/temperature に転送する (SERIAL_ENABLED=True 必須)
 *
 *  修正履歴:
 *    2026-01     I: 側 初版 (稼働実績あり)
 *    2026-07-30  Z: 統合、以下 2 点を修正:
 *      - ESP32 Arduino Core v2.x/v3.x 両対応の ESP-NOW 受信コールバック
 *      - WiFi.macAddress()[0] の表示バグ修正 (String indexing → uint8_t 配列)
 *    2026-08-15  3 層分離アーキテクチャに整合:
 *      - MASTER_DEVICE_ID ハードコード撤廃、MAC 由来 "MST-XXXXXX" に自動生成
 *      - 起動時 master_hello、60 秒ごと master_status を Serial に送出
 *        → Pi 側 serial_reader が受け取り device_nicknames に自己登録、
 *           ダッシュボード管理画面に自動で現れる。全 Master 共通スケッチ化。
 *    2026-09-05  SensorData に battery_voltage / battery_mode を追加 (見落としの修正):
 *      - 子機 (ESP32C3_ESPNOW_Battery_Sensor) の構造体には元から有ったが
 *        Master 側に無く、memcpy で切り詰められて電池電圧が捨てられていた
 *      - ESP32_ESPNOW_Sensor (常時給電) も同じ構造体に揃えた (0.0 / false 固定)
 *      - 受信時に len != sizeof(SensorData) を弾くチェックを追加
 *      - Pi へ転送する JSON に voltage / battery_mode を追加
 *      ★3 スケッチの SensorData は常に同一に保つこと
 * ============================================================
 */

#include <esp_now.h>
#include <WiFi.h>
#include <ArduinoJson.h>

#define BAUD_RATE 115200
#define STATUS_INTERVAL_MS 60000UL   // 60 秒ごとに master_status 送出

// ESP-NOW で受信するセンサーデータ構造 (子機側と一致必須、変更禁止)
typedef struct {
    char sensor_id[16];      // "NOW-A1B2C3" など
    char sensor_name[32];    // "DS18B20-01" など
    float temp;              // 温度 (℃)
    float humidity;          // 湿度 (%)
    int8_t rssi;             // 信号強度 (dBm)
    uint32_t timestamp;      // タイムスタンプ
    float battery_voltage;   // 電池電圧 (V)。常時給電機は 0.0
    bool  battery_mode;      // 電池低下なら true。常時給電機は false
} SensorData;

// グローバル
SensorData received_data[10];
int data_count = 0;
unsigned long last_send_time = 0;
unsigned long last_status_time = 0;

// MAC 由来の Master ID (setup で生成)
char master_id[16];        // "MST-A1B2C3"
char master_mac[18];       // "2C:BC:BB:4D:99:BC"

// ============================================================
//  ESP-NOW 受信コールバック
//  ESP32 Arduino Core v3.0.0 で API シグネチャが変わったので両対応
// ============================================================
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
void on_data_recv(const esp_now_recv_info *recv_info, const uint8_t *incomingData, int len) {
    const uint8_t *src_mac = recv_info->src_addr;
    int8_t packet_rssi = recv_info->rx_ctrl->rssi;
#else
void on_data_recv(const uint8_t *src_mac, const uint8_t *incomingData, int len) {
    int8_t packet_rssi = 0;
#endif
    // 構造体が子機と一致しているか確認する。
    // 一致しないまま memcpy すると境界外を読むので、ここで弾く。
    if (len != (int)sizeof(SensorData)) {
        Serial.printf("[ESP-NOW] !! struct size mismatch: received=%d expected=%u  "
                      "(子機と Master の SensorData を揃えてください)\n",
                      len, (unsigned)sizeof(SensorData));
        return;
    }
    if (data_count < 10) {
        memcpy(&received_data[data_count], incomingData, sizeof(SensorData));
        if (packet_rssi != 0) {
            received_data[data_count].rssi = packet_rssi;
        }
        data_count++;
        Serial.printf("[ESP-NOW] Received from %02X:%02X:%02X:%02X:%02X:%02X RSSI=%d\n",
            src_mac[0], src_mac[1], src_mac[2],
            src_mac[3], src_mac[4], src_mac[5],
            packet_rssi);
    }
}

// ============================================================
//  Pi 側に「自分は誰か」を伝える 2 種類の JSON
//  serial_reader.py 側で type フィールドで判別する
// ============================================================

// 起動時 1 回だけ (Pi が既に動いていた場合の登録用)
void send_master_hello() {
    StaticJsonDocument<256> doc;
    doc["type"] = "master_hello";
    doc["device_id"] = master_id;
    doc["mac"] = master_mac;
    doc["firmware"] = "ESP32_ESPNOW_Master 2026-09-05";
    doc["struct_size"] = (int)sizeof(SensorData);
    serializeJson(doc, Serial);
    Serial.println();
}

// 60 秒ごと (Pi が後から起動した場合の登録用 + heartbeat)
void send_master_status() {
    StaticJsonDocument<256> doc;
    doc["type"] = "master_status";
    doc["device_id"] = master_id;
    doc["mac"] = master_mac;
    doc["uptime_ms"] = millis();
    serializeJson(doc, Serial);
    Serial.println();
}

void setup() {
    Serial.begin(BAUD_RATE);
    delay(1000);

    // WiFi 初期化 (ESP-NOW に必須、MAC 読取りにも必要)
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);

    // MAC アドレス取得 → master_id と表示用 mac 文字列を生成
    uint8_t mac[6] = {0};
    WiFi.macAddress(mac);
    snprintf(master_id, sizeof(master_id), "MST-%02X%02X%02X",
             mac[3], mac[4], mac[5]);
    snprintf(master_mac, sizeof(master_mac), "%02X:%02X:%02X:%02X:%02X:%02X",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    Serial.println("\n\n=== ESP32 Master (ESP-NOW, MAC-based ID) ===");
    Serial.printf("MAC        : %s\n", master_mac);
    Serial.printf("device_id  : %s\n", master_id);

    // ESP-NOW 初期化
    if (esp_now_init() != ESP_OK) {
        Serial.println("ERROR: ESP-NOW initialization failed");
        return;
    }
    esp_now_register_recv_cb(on_data_recv);

    Serial.println("Status: Ready to receive ESP-NOW data");

    // 起動時に一度だけ master_hello を送出 (Pi が動作中なら即登録される)
    send_master_hello();
    last_status_time = millis();

    Serial.println("Waiting for sensor data...\n");
}

void loop() {
    unsigned long current_time = millis();

    // 1 秒ごとにセンサーデータを Pi に転送
    if (current_time - last_send_time >= 1000) {
        if (data_count > 0) {
            send_to_raspberry();
            data_count = 0;
        }
        last_send_time = current_time;
    }

    // 60 秒ごとに heartbeat (Pi が後から起動しても検知できるように)
    if (current_time - last_status_time >= STATUS_INTERVAL_MS) {
        send_master_status();
        last_status_time = current_time;
    }

    delay(10);
}

void send_to_raspberry() {
    StaticJsonDocument<512> doc;
    doc["device_id"] = master_id;      // MAC 由来 (旧: "ESP32_MAIN")
    doc["timestamp"] = millis();

    JsonArray sensors = doc.createNestedArray("sensors");
    for (int i = 0; i < data_count; i++) {
        JsonObject sensor = sensors.createNestedObject();
        sensor["sensor_id"] = received_data[i].sensor_id;
        sensor["sensor_name"] = received_data[i].sensor_name;
        sensor["temperature"] = received_data[i].temp;
        sensor["humidity"] = received_data[i].humidity;
        sensor["rssi"] = received_data[i].rssi;
        sensor["voltage"] = received_data[i].battery_voltage;
        sensor["battery_mode"] = received_data[i].battery_mode ? 1 : 0;
    }

    serializeJson(doc, Serial);
    Serial.println();
}
