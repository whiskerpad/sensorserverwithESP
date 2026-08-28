/**
 * ============================================================
 *  ESP32 + DS18B20 温度センサー (電池運用、WiFi 直接 POST + DeepSleep 版)
 * ============================================================
 *
 *  設計方針: 3 層分離アーキテクチャ (2026-07-30 導入)
 *    - 識別    = MAC 由来の device_id を自動生成 (per-chip 書換え不要)
 *    - IP割当  = Pi 側 dnsmasq の DHCP 予約
 *    - 表示名  = Flask の nickname テーブル
 *    詳細は outputs/docs/デバイス識別設計.md
 *
 *  【重要】このスケッチは全チップ共通、書換え不要でコピペ書込み可能
 *
 *  ハードウェア:
 *    - ESP32 (WROOM-DA 等、常時給電/電池自動判別)
 *    - DS18B20 (GPIO4)
 *    - 電池電圧検出: GPIO35 (ADC7) に分圧回路
 *
 *  更新履歴:
 *    2026-07-28 修正 A/B (JSON 384、フィールド追加)
 *    2026-07-30 3 層分離アーキテクチャに切替 (MAC ベース device_id)
 * ============================================================
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <esp_sleep.h>

// ===== WiFi 設定 (全チップ共通) =====
const char* ssid = "YOUR_AP_SSID_HERE";
const char* password = "YOUR_AP_PASSWORD_HERE";
const char* serverUrl = "http://192.168.4.1:5000/api/temperature";

// ===== DS18B20 設定 =====
#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ===== 電源検出 =====
#define POWER_SOURCE_PIN 35  // GPIO35 (ADC7) でバッテリー電圧検出
bool isBatteryMode = false;

// ===== タイミング =====
// ------------------------------------------------------------
// 【測定周期の変更方法】
//   下 2 つの定数を書換えるだけ (両方揃えて変更する)。単位に注意:
//     MEASURE_INTERVAL  = ミリ秒       (ms、常時給電時 millis() 判定用)
//     SLEEP_DURATION_US = マイクロ秒   (μs、電池 DeepSleep 用、末尾 ULL 必須)
//
//   計算:  MEASURE_INTERVAL  = 秒 × 1000
//          SLEEP_DURATION_US = 秒 × 1000000
//
//   例:
//     30 秒周期 → 30000       / 30000000ULL
//     60 秒周期 → 60000       / 60000000ULL      ← 現行値
//     5  分周期 → 300000      / 300000000ULL
//     10 分周期 → 600000      / 600000000ULL
//     30 分周期 → 1800000     / 1800000000ULL
//     1  時間周期 → 3600000   / 3600000000ULL
//
//   周期を長くすると電池寿命が伸びる。逆に短いと詰まる (WiFi 接続 + POST に
//   毎回 3-5 秒かかるので、30 秒未満は非推奨)。
//   ログの "Entering deep sleep for 60 seconds..." 表記も一緒に書換えると綺麗。
// ------------------------------------------------------------
#define MEASURE_INTERVAL 60000            // 60 秒 (常時給電時 millis 判定)
#define SLEEP_DURATION_US 60000000ULL     // 60 秒 (電池 DeepSleep)
#define MAX_RETRIES 3

// ===== グローバル =====
char deviceId[16];   // "ESP-A1B2C3"、setup() 内で MAC から生成
unsigned long lastMeasureTime = 0;
int retryCount = 0;
float g_voltage = 0.0;
int g_batteryPercent = 100;


void setup() {
    Serial.begin(115200);
    delay(2000);

    // ===== 2026-08-16 バッテリー消耗回帰修正 =====
    // 旧: ここで WiFi.mode(WIFI_STA) → MAC 取得 → その後 connectToWiFi() で
    //     WiFi.mode(OFF) → 再 STA → begin() の 2 度起動になり、電池消耗が
    //     従来比 30-40% 悪化していた (以前 1 か月保った電池が数日で切れる)。
    // 新: setup では WiFi に触れず、電源判定・DS18B20 初期化まで。
    //     WiFi は connectToWiFi() 内で 1 回だけ起動し、そこで MAC を取る。

    detectPowerSource();
    initializeSensors();
    connectToWiFi();          // ← この中で WiFi 起動 + MAC 取得 + device_id 生成
    if (WiFi.status() == WL_CONNECTED) {
        WiFi.setTxPower(WIFI_POWER_8_5dBm);
    }
}

void loop() {
    // ===== 2026-08-16 電池モード最適化 =====
    // 旧: wake 直後の loop で millis() が MEASURE_INTERVAL (60 秒) 経過するまで
    //     WiFi ON のまま待機してから測定 → DeepSleep していた。
    //     結果、実効周期 120 秒 + 60 秒/cycle の WiFi ON 待機で電池を無駄消費。
    // 新: 電池モードは wake 直後に即測定 → 即 DeepSleep で待機ゼロ。
    //     AC/USB 給電時のみ従来の millis() インターバル方式を残す。

    if (isBatteryMode) {
        if (WiFi.status() != WL_CONNECTED) {
            Serial.println("WiFi lost, reconnecting...");
            connectToWiFi();
        }
        measureAndSend();
        Serial.println("Entering deep sleep for 60 seconds...");
        Serial.flush();
        esp_sleep_enable_timer_wakeup(SLEEP_DURATION_US);
        esp_deep_sleep_start();
        return;   // 到達しないが念のため
    }

    // 常時給電 (USB/AC) の場合は従来通り millis() で周期回し
    if (millis() - lastMeasureTime >= MEASURE_INTERVAL) {
        lastMeasureTime = millis();
        if (WiFi.status() != WL_CONNECTED) {
            connectToWiFi();
        }
        measureAndSend();
    }
    delay(1000);
}

void detectPowerSource() {
    int adc = analogRead(POWER_SOURCE_PIN);
    g_voltage = (adc / 4095.0) * 4.3;
    isBatteryMode = (g_voltage < 2.5);
    g_batteryPercent = (int)(((g_voltage - 2.5) / 0.8) * 100.0);
    if (g_batteryPercent < 0) g_batteryPercent = 0;
    if (g_batteryPercent > 100) g_batteryPercent = 100;
    Serial.printf("[POWER] adc=%d voltage=%.2fV battery=%d%% is_battery=%s\n",
                  adc, g_voltage, g_batteryPercent, isBatteryMode ? "true" : "false");
}

void initializeSensors() {
    sensors.begin();
    int deviceCount = sensors.getDeviceCount();
    Serial.printf("DS18B20 detected: %d\n", deviceCount);
    if (deviceCount == 0) {
        Serial.println("WARNING: No DS18B20 sensors found");
    }
    sensors.setResolution(12);
}

void connectToWiFi() {
    // 2026-08-16: setup での WiFi 早期起動を廃止したので、ここが唯一の WiFi ON
    // (再接続時は既に STA モードでいるので mode 切替の余分な delay を回避)
    if (WiFi.getMode() != WIFI_STA) {
        WiFi.mode(WIFI_STA);
        delay(100);
    }

    // device_id が未生成なら (初回起動) ここで MAC 取得して生成
    if (deviceId[0] == '\0') {
        uint8_t mac[6] = {0};
        WiFi.macAddress(mac);
        snprintf(deviceId, sizeof(deviceId), "ESP-%02X%02X%02X",
                 mac[3], mac[4], mac[5]);
        Serial.printf("MAC: %02X:%02X:%02X:%02X:%02X:%02X → device_id: %s\n",
                      mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], deviceId);
    }

    Serial.printf("Connecting to WiFi: %s (DHCP, dnsmasq reservation)\n", ssid);
    WiFi.begin(ssid, password);

    int attempts = 0;
    const int maxAttempts = 40;
    while (WiFi.status() != WL_CONNECTED && attempts < maxAttempts) {
        delay(500);
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("WiFi connected: ip=%s rssi=%d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
        Serial.printf("Failed to connect. status=%d\n", WiFi.status());
    }
}

void measureAndSend() {
    detectPowerSource();
    sensors.requestTemperatures();
    float temperature = sensors.getTempCByIndex(0);

    if (temperature == DEVICE_DISCONNECTED_C || temperature == 85.0 || temperature == -127.0) {
        Serial.println("ERROR: sensor read failed");
        return;
    }
    Serial.printf("Temperature: %.2f C\n", temperature);

    if (WiFi.status() == WL_CONNECTED) {
        sendTemperatureData(temperature);
    }
}

void sendTemperatureData(float temperature) {
    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    DynamicJsonDocument doc(384);
    doc["device_id"] = deviceId;
    doc["name"] = deviceId;
    doc["temperature"] = round(temperature * 100) / 100.0;
    doc["temp"] = round(temperature * 100) / 100.0;
    doc["ip_address"] = WiFi.localIP().toString();
    doc["voltage"] = round(g_voltage * 100) / 100.0;
    doc["battery_percent"] = g_batteryPercent;
    doc["battery_mode"] = isBatteryMode ? 1 : 0;
    doc["rssi"] = WiFi.RSSI();
    doc["signal_strength"] = WiFi.RSSI();

    String jsonString;
    serializeJson(doc, jsonString);
    Serial.printf("Payload (%d bytes): %s\n", jsonString.length(), jsonString.c_str());

    int httpResponseCode = http.POST(jsonString);
    if (httpResponseCode > 0) {
        Serial.printf("HTTP %d\n", httpResponseCode);
        retryCount = 0;
    } else {
        Serial.printf("POST error: %d\n", httpResponseCode);
        retryCount++;
        if (retryCount >= MAX_RETRIES) retryCount = 0;
    }
    http.end();
}
