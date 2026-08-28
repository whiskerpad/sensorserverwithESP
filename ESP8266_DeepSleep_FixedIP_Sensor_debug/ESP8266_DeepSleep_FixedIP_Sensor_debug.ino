/**
 * ============================================================
 *  ESP-WROOM-02 + DS18B20 (デバッグ版: Serial 出力有効)
 *      → DeepSleep 定期間隔で Raspberry Pi (Flask AP) へ HTTP POST
 * ============================================================
 *
 *  本番版 (ESP8266_DeepSleep_FixedIP_Sensor.ino) と設計方針は同じ:
 *    - 識別    = MAC 由来の device_id を自動生成
 *    - IP割当  = Pi 側 dnsmasq の DHCP 予約
 *    - 表示名  = Flask の nickname テーブル
 *    詳細は outputs/docs/デバイス識別設計.md
 *
 *  本番版との差分 (このファイルだけの変更):
 *    - Serial.begin(115200) 後に各段階で Serial.println / printf 出力
 *    - DeepSleep 直前に Serial.flush() で buffer を吐き切る
 *
 *  使い方:
 *    1) Arduino IDE のシリアルモニタを 115200 bps で開く
 *    2) このスケッチを書き込む
 *    3) 30-120 秒周期で BOOT → SENSOR → POWER → WIFI → HTTP → SLEEP のログが繰り返される
 *
 *  更新履歴:
 *    2026-07-16 初版
 *    2026-07-30 3 層分離アーキテクチャに切替 (MAC ベース device_id)
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

#define ONE_WIRE_BUS 4
#define POWER_SOURCE_PIN A0
// 【測定周期の変更方法】単位 μs、"e6" = ×1,000,000
//   30s→30e6 (現行、デバッグ用に短周期) / 60s→60e6 / 2分→120e6 / 5分→300e6 / 1時間→3600e6
//   ESP8266 最大 DeepSleep 約 71 分 (4294e6 μs)
#define DEEP_SLEEP_INTERVAL 30e6  // 30秒 (デバッグしやすい短周期)

const char* apSSID = "YOUR_AP_SSID_HERE";
const char* apPassword = "YOUR_AP_PASSWORD_HERE";
const char* serverURL = "http://192.168.4.1:5000/api/temperature";
const int HTTP_TIMEOUT = 5000;

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
WiFiClient wifiClient;

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println();
    Serial.println();
    Serial.println("========================================");
    Serial.println("[BOOT] ESP-WROOM-02 DeepSleep (DEBUG, MAC-based ID)");
    Serial.printf("[BOOT] chip_id=0x%06X flash_size=%u\n",
                  ESP.getChipId(), ESP.getFlashChipRealSize());
    Serial.printf("[BOOT] reset_reason=%s\n", ESP.getResetReason().c_str());

    // MAC 由来 device_id を生成
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char deviceId[16];
    snprintf(deviceId, sizeof(deviceId), "ESP-%02X%02X%02X",
             mac[3], mac[4], mac[5]);
    Serial.printf("[BOOT] full_mac=%s\n", WiFi.macAddress().c_str());
    Serial.printf("[BOOT] device_id=%s (MAC lower 3 bytes)\n", deviceId);
    Serial.println("========================================");

    delay(500);

    Serial.println("[SENSOR] initializing DS18B20...");
    sensors.begin();
    int deviceCount = sensors.getDeviceCount();
    Serial.printf("[SENSOR] detected device_count=%d\n", deviceCount);

    for (int i = 0; i < deviceCount; i++) {
        DeviceAddress addr;
        if (sensors.getAddress(addr, i)) {
            Serial.printf("[SENSOR] #%d ROM=", i);
            for (int j = 0; j < 8; j++) Serial.printf("%02X", addr[j]);
            Serial.println();
        }
    }
    if (deviceCount == 0) {
        Serial.println("[SENSOR] !! WARNING: no DS18B20. Check wiring / 4.7kΩ pull-up");
    }

    sensors.setResolution(12);
    Serial.println("[SENSOR] resolution=12bit, requesting temperature...");
    sensors.requestTemperatures();
    delay(800);
    float temp = sensors.getTempCByIndex(0);
    Serial.printf("[SENSOR] raw temp=%.4f C\n", temp);

    if (temp == DEVICE_DISCONNECTED_C || temp == -127.0 || temp == 85.0) {
        Serial.printf("[SENSOR] !! ERROR: invalid reading (%.2f) → sending flag -999\n", temp);
        temp = -999.0;
    }

    int adcValue = analogRead(POWER_SOURCE_PIN);
    float voltage = (adcValue / 1023.0) * 4.3;
    bool isBatteryMode = (voltage < 3.5);
    float batteryPercent = ((voltage - 2.5) / 0.8) * 100.0;
    if (batteryPercent < 0.0) batteryPercent = 0.0;
    if (batteryPercent > 100.0) batteryPercent = 100.0;

    Serial.printf("[POWER] adc=%d voltage=%.2fV battery=%d%% is_battery=%s\n",
                  adcValue, voltage, (int)batteryPercent,
                  isBatteryMode ? "true" : "false");

    // WiFi 接続 (静的 IP、方式 D: MAC 下位バイトから IP 導出)
    // 2026-08-21: DHCP → 静的 IP に戻す (電池寿命 2 週間 → 1 か月+ 復帰目的)
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.setPhyMode(WIFI_PHY_MODE_11N);

    IPAddress fixedIP(192, 168, 4, 100 + (mac[5] & 0x7F));
    IPAddress gateway(192, 168, 4, 1);
    IPAddress subnet(255, 255, 255, 0);
    WiFi.config(fixedIP, gateway, subnet);
    Serial.printf("[WIFI] target SSID=\"%s\", static IP=%s (derived from MAC[5]=0x%02X)\n",
                  apSSID, fixedIP.toString().c_str(), mac[5]);
    delay(100);
    WiFi.begin(apSSID, apPassword);

    Serial.print("[WIFI] connecting");
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WIFI] connected ip=%s rssi=%d dBm attempts=%d\n",
                      WiFi.localIP().toString().c_str(),
                      WiFi.RSSI(), attempts);
    } else {
        Serial.printf("[WIFI] !! FAILED status=%d attempts=%d\n",
                      WiFi.status(), attempts);
        goto sleep;
    }

    if (temp != -999.0) {
        StaticJsonDocument<384> doc;
        doc["device_id"] = deviceId;
        doc["name"] = deviceId;
        doc["temperature"] = round(temp * 100) / 100.0;
        doc["temp"] = round(temp * 100) / 100.0;
        doc["ip_address"] = WiFi.localIP().toString();
        doc["voltage"] = round(voltage * 100) / 100.0;
        doc["battery_percent"] = (int)batteryPercent;
        doc["battery_mode"] = isBatteryMode ? 1 : 0;
        doc["rssi"] = WiFi.RSSI();
        doc["signal_strength"] = WiFi.RSSI();

        String payload;
        serializeJson(doc, payload);
        Serial.printf("[HTTP] POST %s\n", serverURL);
        Serial.printf("[HTTP] payload: %s\n", payload.c_str());

        HTTPClient http;
        http.setTimeout(HTTP_TIMEOUT);
        if (http.begin(wifiClient, serverURL)) {
            http.addHeader("Content-Type", "application/json");
            unsigned long t0 = millis();
            int httpCode = http.POST(payload);
            unsigned long elapsed = millis() - t0;
            if (httpCode > 0) {
                Serial.printf("[HTTP] response code=%d elapsed=%lu ms\n", httpCode, elapsed);
                String resp = http.getString();
                if (resp.length() > 0) Serial.printf("[HTTP] body: %s\n", resp.c_str());
            } else {
                Serial.printf("[HTTP] !! POST failed code=%d error=%s\n",
                              httpCode, http.errorToString(httpCode).c_str());
            }
            http.end();
        } else {
            Serial.println("[HTTP] !! http.begin() failed");
        }
    } else {
        Serial.println("[HTTP] skipping POST (sensor error)");
    }

sleep:
    Serial.println("[SLEEP] disconnecting WiFi and entering DeepSleep");
    Serial.flush();
    delay(100);
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(500);
    ESP.deepSleep(DEEP_SLEEP_INTERVAL, WAKE_RF_DEFAULT);
}

void loop() {}
