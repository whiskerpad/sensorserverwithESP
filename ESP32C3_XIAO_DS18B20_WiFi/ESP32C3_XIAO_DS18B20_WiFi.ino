/**
 * ============================================================
 *  Seeed Studio XIAO ESP32-C3 + DS18B20 温度センサー (LiPo 電池駆動)
 *      → WiFi 直接 POST + DeepSleep 版
 * ============================================================
 *
 *  ベース: I:\環境データ収集システム\esp_now_master_and_sensor\
 *          ESP32C3_Battery_Sensor\WiFiESP32C3_Battery_Sensor_WiFi\
 *          ESP32C3_Battery_Sensor_WiFi.ino (稼働実績あり、現地展開済)
 *
 *  対象ハード:
 *    - Seeed Studio XIAO ESP32-C3
 *    - LiPo 電池 3.7V (満充電 4.2V、放電下限 3.0V)
 *    - DS18B20 温度センサー (GPIO4 = D2 に配線)
 *      (旧コメントに "GPIO0 = D0" とあったが XIAO ESP32-C3 は GPIO0 が
 *       外部未引出しのため事実誤認。2026-08-16 GPIO4 に訂正・統一)
 *    - バッテリー分圧: BAT+ → 270kΩ → A1 (GPIO3) → 270kΩ → GND (1:1 分圧)
 *
 *  Arduino IDE ボード設定:
 *    - Board: "XIAO_ESP32C3" (Seeed Studio セクション)
 *    - USB CDC On Boot: Enabled
 *    - Flash Size: 4MB, Partition: Default
 *
 *  3 層分離アーキテクチャ (2026-07-30 導入) の反映点:
 *    - sensor_id は MAC 由来で自動生成 (例: ESP-A1B2C3)
 *      → 元の SENSOR_ID "ESP32C3_BATTERY_01" ハードコードを廃止
 *      → 全チップ共通スケッチとして per-chip 書換え不要に
 *    - IP は Pi 側 dnsmasq の DHCP 予約で管理 (WiFi.config は使わない)
 *    - 表示名は Flask ダッシュボードの nickname テーブルで管理
 *
 *  【変更しなかった項目 (稼働実績を尊重)】:
 *    - DS18B20 は GPIO4 = D2 (XIAO/無印 ESP32 共通で使えるピン、GPIO0 は XIAO C3 では未引出し)
 *    - 電圧測定は analogReadMilliVolts() で 16 サンプル平均 (自動キャリブレーション)
 *    - 分圧補正 ×2.0 (1:1 分圧回路)
 *    - LiPo 低下閾値 3.0V
 *    - JSON フィールド名 (sensor_id, sensor_name, temp, battery_voltage, battery_mode as bool)
 *      → Flask 側は sensor_id/device_id と temp/temperature の両方受理するため互換性維持
 *    - 送信間隔 60 秒
 *    - DeepSleep 移行は loop() 内 (setup() 完了後)
 *
 *  更新履歴:
 *    2026-01     初版 (I: 側、現地稼働実績あり)
 *    2026-07-30  Z: 統合、MAC ベース sensor_id 自動生成に変更 (3 層分離)
 * ============================================================
 */

#include <WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===== 設定 =====
#define ONE_WIRE_BUS 4        // DS18B20 データピン (GPIO4 = D2、XIAO/無印 ESP32 共通で使える)
#define BATTERY_ADC_PIN A1    // バッテリー監視 (A1/GPIO3、GPIO2/A0 はストラッピング回避)
#define SENSOR_NAME "DS18B20-Battery"   // nickname 未設定時のフォールバック表示名
// ------------------------------------------------------------
// 【測定周期の変更方法】 単位: 秒。値を書換えるだけ (goToDeepSleep 内で ×1e6 して μs に変換)
//   30 秒周期 → 30 / 60 秒 → 60 (現行) / 5 分 → 300 / 10 分 → 600 / 30 分 → 1800 / 1 時間 → 3600
//   周期を長くすると電池寿命が伸びる。30 秒未満は WiFi 接続 + POST 3-5 秒がボトルネックで非推奨。
// ------------------------------------------------------------
#define SEND_INTERVAL 60      // 60 秒ごとに送信 (電池駆動、秒単位)

// WiFi 設定
const char* ssid = "YOUR_AP_SSID_HERE";
const char* password = "YOUR_AP_PASSWORD_HERE";
const char* serverURL = "http://192.168.4.1:5000/api/temperature";

// OneWire と DallasTemperature インスタンス
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// MAC 由来の sensor_id (setup で生成、loop から参照)
char sensor_id[16];


// ===== バッテリー検出関数 =====
// XIAO ESP32C3 用 - 分圧回路 (BAT+ -> 270k -> A1 -> 270k -> GND)
// 自動キャリブレーション対応 (analogReadMilliVolts)
float getBatteryVoltage() {
    uint32_t sumVoltage = 0;
    for (int i = 0; i < 16; i++) {
        sumVoltage += analogReadMilliVolts(BATTERY_ADC_PIN);
        delayMicroseconds(50);
    }
    float averageMilliV = sumVoltage / 16.0;
    // 1:1 分圧なので実電圧は 2 倍
    float batteryVoltage = (averageMilliV / 1000.0) * 2.0;
    return batteryVoltage;
}

// LiPo バッテリー低下判定 (3.0V 未満で低下)
bool isBatteryLow(float voltage) {
    return voltage < 3.0;
}


void setup() {
    Serial.begin(115200);
    delay(1000);

    // ===== 2026-08-16 バッテリー消耗回帰修正 =====
    // 旧: setup 序盤で WiFi.mode(WIFI_STA) → MAC 取得 → WiFi.mode(WIFI_OFF)
    //     の 1 サイクルを追加していたため、WiFi ラジオが 2 度起動していた。
    //     これで 1 か月保っていた電池が数日で消耗する回帰があった。
    // 新: setup では WiFi に一切触らず、DS18B20 とバッテリー電圧だけ扱う。
    //     MAC 取得と sensor_id 生成は loop() → sendDataViaWiFi() 内の
    //     WiFi.begin() 直後に 1 回だけ行う (WiFi 起動 1 回に統合)。

    Serial.println("\n\n=== XIAO ESP32C3 Sensor with Battery (DS18B20) - WiFi ===");
    Serial.println("Sensor Name: " + String(SENSOR_NAME));
    Serial.println("Mode:        Battery Powered (60 sec interval)");
    Serial.println("DS18B20 Pin: GPIO" + String(ONE_WIRE_BUS));
    Serial.println("Battery ADC: A1 (GPIO3)");

    // DS18B20 初期化 (WiFi 無関係、ラジオ OFF 状態でよい)
    sensors.begin();
    int deviceCount = sensors.getDeviceCount();
    Serial.print("DS18B20 Found: ");
    Serial.println(deviceCount);
    if (deviceCount == 0) {
        Serial.println("ERROR: No DS18B20 sensor found!");
        delay(2000);
        goToDeepSleep();
    }

    // バッテリー電圧表示 (診断用、ラジオ OFF なので低消費)
    float battVoltage = getBatteryVoltage();
    Serial.printf("Battery Voltage: %.2fV %s\n",
                  battVoltage, isBatteryLow(battVoltage) ? "(LOW)" : "(GOOD)");
}


void loop() {
    // DS18B20 から温度読取り
    sensors.requestTemperatures();
    delay(100);
    float temp = sensors.getTempCByIndex(0);

    if (temp == DEVICE_DISCONNECTED_C) {
        Serial.println("ERROR: DS18B20 disconnected or not responding");
        goToDeepSleep();
        return;
    }
    Serial.printf("Temperature: %.2f C\n", temp);

    // WiFi 経由で送信
    sendDataViaWiFi(temp);

    // Deep Sleep へ (60 秒)
    goToDeepSleep();
}


// WiFi 経由で Pi サーバーに送信
void sendDataViaWiFi(float temperature) {
    // WiFi 起動 1 サイクル (2026-08-16 修正: MAC 取得もこの中で行う)
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    // MAC ベース sensor_id 生成 (WiFi.begin 後は macAddress() が有効)
    // sensor_id はグローバルなので、初回だけ生成すれば OK
    if (sensor_id[0] == '\0') {
        uint8_t mac[6] = {0};
        WiFi.macAddress(mac);
        snprintf(sensor_id, sizeof(sensor_id), "ESP-%02X%02X%02X",
                 mac[3], mac[4], mac[5]);
        Serial.printf("MAC: %02X:%02X:%02X:%02X:%02X:%02X → sensor_id=%s\n",
                      mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], sensor_id);
    }

    Serial.print("Connecting to WiFi: ");
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println(" FAILED");
        WiFi.mode(WIFI_OFF);
        return;
    }
    Serial.printf("\nConnected! IP=%s RSSI=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());

    // JSON ペイロード作成 (I: 版の field 命名を継承、Flask は互換対応)
    float battVoltage = getBatteryVoltage();

    StaticJsonDocument<256> doc;
    doc["sensor_id"] = sensor_id;              // MAC 由来 (旧: ハードコード)
    doc["sensor_name"] = SENSOR_NAME;
    doc["temp"] = temperature;
    doc["humidity"] = 0.0;                     // DS18B20 は湿度なし
    doc["rssi"] = WiFi.RSSI();
    doc["timestamp"] = millis();
    doc["battery_voltage"] = battVoltage;
    doc["battery_mode"] = isBatteryLow(battVoltage);   // true = low, false = good

    String jsonData;
    serializeJson(doc, jsonData);

    // HTTP POST
    HTTPClient http;
    http.begin(serverURL);
    http.addHeader("Content-Type", "application/json");
    int httpResponseCode = http.POST(jsonData);
    Serial.printf("HTTP %d\n", httpResponseCode);
    if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.println("Response: " + response);
    }
    http.end();

    WiFi.mode(WIFI_OFF);
}


// Deep Sleep へ (60 秒)
void goToDeepSleep() {
    Serial.printf("Going to Deep Sleep for %d seconds...\n", SEND_INTERVAL);
    Serial.flush();
    esp_sleep_enable_timer_wakeup((uint64_t)SEND_INTERVAL * 1000000ULL);
    esp_deep_sleep_start();
}
