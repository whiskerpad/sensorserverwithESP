/**
 * ============================================================
 *  ESP32 + DS18B20 温度センサー (常時給電、WiFi 直接 POST 版)
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
 *  新チップ追加手順:
 *    1) Get_MAC_Address.ino で新チップの MAC を確認
 *    2) Pi 側 /etc/dnsmasq.d/wlan1.conf に dhcp-host= の 1 行追加
 *    3) このスケッチをコピペで書込む
 *    4) ダッシュボード管理画面で nickname 割当
 *
 *  更新履歴:
 *    2026-07-28 修正 A/B (JSON 384、フィールド追加)
 *    2026-07-30 3 層分離アーキテクチャに切替 (MAC ベース device_id)
 *               事前 WiFi スキャンを削除して起動時間短縮
 * ============================================================
 */

#include <OneWire.h>
#include <DallasTemperature.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===== WiFi 設定 (全チップ共通) =====
const char* ssid = "YOUR_AP_SSID_HERE";
const char* password = "YOUR_AP_PASSWORD_HERE";
const char* serverUrl = "http://192.168.4.1:5000/api/temperature";

// ===== DS18B20 設定 =====
#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ===== タイミング =====
#define MEASURE_INTERVAL 30000
#define MAX_RETRIES 3

// ===== グローバル =====
char deviceId[16];   // "ESP-A1B2C3"、setup() 内で MAC から生成
unsigned long lastMeasureTime = 0;
int retryCount = 0;


void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n\n================================");
    Serial.println("ESP32 DS18B20 WiFi (MAC-based ID)");
    Serial.println("================================");

    // WiFi 初期化 (ESP32-C3 では MAC 読み取り前に必要、ESP32 でも安全)
    WiFi.mode(WIFI_STA);
    delay(100);

    // device_id を MAC から自動生成
    uint8_t mac[6] = {0};
    WiFi.macAddress(mac);
    snprintf(deviceId, sizeof(deviceId), "ESP-%02X%02X%02X",
             mac[3], mac[4], mac[5]);
    Serial.printf("Full MAC: %s\n", WiFi.macAddress().c_str());
    Serial.printf("Device ID (auto): %s\n\n", deviceId);

    initializeSensors();
    connectToWiFi();
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi lost, reconnecting...");
        connectToWiFi();
    }
    if (millis() - lastMeasureTime >= MEASURE_INTERVAL) {
        lastMeasureTime = millis();
        measureAndSend();
    }
    delay(1000);
}

void initializeSensors() {
    Serial.println("Initializing DS18B20 sensors...");
    sensors.begin();
    int deviceCount = sensors.getDeviceCount();
    Serial.printf("Found %d device(s)\n", deviceCount);
    if (deviceCount == 0) {
        Serial.println("WARNING: No DS18B20 sensors found. Check wiring & 4.7k pull-up.");
    }
    sensors.setResolution(12);
    Serial.println("Resolution: 12-bit (0.0625C)");
}

void connectToWiFi() {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(500);
    WiFi.mode(WIFI_STA);
    delay(100);
    WiFi.setAutoReconnect(true);
    WiFi.persistent(true);

    Serial.printf("\nConnecting to WiFi: %s (DHCP, dnsmasq reservation expected)\n", ssid);
    WiFi.begin(ssid, password);

    int attempts = 0;
    const int maxAttempts = 120;  // 60 秒
    while (WiFi.status() != WL_CONNECTED && attempts < maxAttempts) {
        delay(500);
        attempts++;
        if (attempts % 4 == 0) {
            Serial.printf("[%ds] status=%d rssi=%d\n",
                          attempts / 2, WiFi.status(), WiFi.RSSI());
        }
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("WiFi connected: ip=%s rssi=%d dBm\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
        Serial.printf("Failed to connect. status=%d\n", WiFi.status());
    }
}

void measureAndSend() {
    Serial.printf("\n--- Measurement at %lus ---\n", millis() / 1000);
    sensors.requestTemperatures();
    float temperature = sensors.getTempCByIndex(0);

    if (temperature == DEVICE_DISCONNECTED_C || temperature == 85.0 || temperature == -127.0) {
        Serial.println("ERROR: sensor read failed");
        return;
    }
    Serial.printf("Temperature: %.2f C\n", temperature);

    if (WiFi.status() == WL_CONNECTED) {
        sendTemperatureData(temperature);
    } else {
        Serial.println("WiFi not connected, skipping POST");
    }
}

void sendTemperatureData(float temperature) {
    HTTPClient http;
    Serial.printf("POST %s\n", serverUrl);

    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    // JSON バッファ 384 バイト、全フィールド送信
    DynamicJsonDocument doc(384);
    doc["device_id"] = deviceId;
    doc["name"] = deviceId;                     // nickname 未設定時のフォールバック
    doc["temperature"] = round(temperature * 100) / 100.0;
    doc["temp"] = round(temperature * 100) / 100.0;
    doc["ip_address"] = WiFi.localIP().toString();
    doc["voltage"] = 5.0;                        // 常時給電の目安 (USB 5V)
    doc["battery_percent"] = 100;
    doc["battery_mode"] = 0;                     // 0 = AC 給電
    doc["rssi"] = WiFi.RSSI();
    doc["signal_strength"] = WiFi.RSSI();

    String jsonString;
    serializeJson(doc, jsonString);
    Serial.printf("Payload (%d bytes): %s\n", jsonString.length(), jsonString.c_str());

    int httpResponseCode = http.POST(jsonString);
    if (httpResponseCode > 0) {
        Serial.printf("HTTP %d\n", httpResponseCode);
        String resp = http.getString();
        if (resp.length() > 0) Serial.println(resp);
        retryCount = 0;
    } else {
        Serial.printf("POST error: %d\n", httpResponseCode);
        retryCount++;
        if (retryCount >= MAX_RETRIES) retryCount = 0;
    }
    http.end();
}
