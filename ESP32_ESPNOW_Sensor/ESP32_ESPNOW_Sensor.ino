/**
 * ============================================================
 *  ESP32 Sensor (ESP-NOW 送信版、常時給電向け)
 *
 *  ベース: I:\...\esp_now_master_and_sensor\ESP32_Sensor_DS18B20\ (稼働実績あり)
 *
 *  修正 (2026-07-30):
 *    - sensor_id を MAC 由来の "NOW-XXXXXX" 形式に自動生成
 *      → WiFi 直接 POST 系 (ESP-XXXXXX) と区別できる命名
 *      → per-chip 書換え不要
 *    - MAC 表示バグ修正 (WiFi.macAddress()[0] は char が返るので uint8_t 配列で取得)
 * ============================================================
 */

#include <esp_now.h>
#include <WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ===== 設定 =====
#define ONE_WIRE_BUS 4        // DS18B20 データピン (GPIO4)
#define SENSOR_NAME "DS18B20-NOW"  // nickname 未設定時のフォールバック表示
#define SEND_INTERVAL 30000   // 30秒ごとに送信

// マスター ESP32 の MAC アドレス (Master 起動時の Serial モニタで確認して書換え)
uint8_t masterMAC[] = {0x2C, 0xBC, 0xBB, 0x4D, 0x99, 0xBC};

// センサーデータ構造 (Master 側と一致させる、変更禁止)
typedef struct {
    char sensor_id[16];       // "NOW-A1B2C3" (MAC 由来、10 文字 + 終端)
    char sensor_name[32];
    float temp;
    float humidity;
    int8_t rssi;
    uint32_t timestamp;
} SensorData;

// MAC 由来 sensor_id (setup で生成、loop から参照)
char sensor_id[16];

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

unsigned long last_send_time = 0;

// ESP-NOW 送信コールバック (ESP32 Core v3.x API、v2.x なら関数シグネチャを変える必要あり)
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
void on_data_sent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
#else
void on_data_sent(const uint8_t *mac_addr, esp_now_send_status_t status) {
#endif
    Serial.print("Send Status: ");
    Serial.println(status == ESP_NOW_SEND_SUCCESS ? "Success" : "Failed");
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    // WiFi 初期化 (ESP-NOW に必須、MAC 読取りにも必要)
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);

    // MAC アドレスを byte 配列で取得
    uint8_t mac[6] = {0};
    WiFi.macAddress(mac);

    // MAC 由来 sensor_id: "NOW-XXXXXX" (下位 3 バイト、6 hex)
    // WiFi 直接 POST 系 "ESP-XXXXXX" と一目で区別できる
    snprintf(sensor_id, sizeof(sensor_id), "NOW-%02X%02X%02X",
             mac[3], mac[4], mac[5]);

    Serial.println("\n\n=== ESP32 Sensor (ESP-NOW, MAC-based ID) ===");
    Serial.printf("MAC:       %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    Serial.printf("sensor_id: %s\n", sensor_id);
    Serial.printf("Sensor name (fallback): %s\n", SENSOR_NAME);

    // DS18B20 初期化
    sensors.begin();
    int deviceCount = sensors.getDeviceCount();
    Serial.print("DS18B20 Found: ");
    Serial.println(deviceCount);
    if (deviceCount == 0) {
        Serial.println("ERROR: No DS18B20 sensor found! Check wiring & 4.7k pull-up");
    }

    // ESP-NOW 初期化
    if (esp_now_init() != ESP_OK) {
        Serial.println("ERROR: ESP-NOW initialization failed");
        return;
    }
    esp_now_register_send_cb(on_data_sent);

    // ピア登録 (Master ESP32)
    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, masterMAC, 6);
    peerInfo.channel = 1;
    peerInfo.encrypt = false;
    if (esp_now_add_peer(&peerInfo) != ESP_OK) {
        Serial.println("Failed to add peer");
        return;
    }
    Serial.println("Master registered");
    Serial.println("Status: Ready to send sensor data\n");
}

void loop() {
    unsigned long current_time = millis();
    if (current_time - last_send_time >= SEND_INTERVAL) {
        send_sensor_data();
        last_send_time = current_time;
    }
    delay(100);
}

void send_sensor_data() {
    sensors.requestTemperatures();
    delay(100);
    float temp = sensors.getTempCByIndex(0);

    if (temp == DEVICE_DISCONNECTED_C) {
        Serial.println("ERROR: DS18B20 disconnected");
        return;
    }

    SensorData sensor_data;
    strncpy(sensor_data.sensor_id, sensor_id, sizeof(sensor_data.sensor_id) - 1);
    sensor_data.sensor_id[sizeof(sensor_data.sensor_id) - 1] = '\0';
    strncpy(sensor_data.sensor_name, SENSOR_NAME, sizeof(sensor_data.sensor_name) - 1);
    sensor_data.sensor_name[sizeof(sensor_data.sensor_name) - 1] = '\0';
    sensor_data.temp = temp;
    sensor_data.humidity = 0.0;
    sensor_data.rssi = WiFi.RSSI();
    sensor_data.timestamp = millis();

    esp_now_send(masterMAC, (uint8_t *)&sensor_data, sizeof(sensor_data));

    Serial.printf("Sent [%s]: Temp=%.2f C\n", sensor_id, temp);
}
