/**
 * ============================================================
 *  ESP-WROOM-02 (技適対応) + DS18B20
 *      → DeepSleep 1分間隔で Raspberry Pi (Flask AP) へ HTTP POST
 * ============================================================
 *
 *  STEP 2 (電池駆動版):
 *    単三電池3本 + HT7333-1 LDO で 3.3V 駆動。
 *    起動 → 電池電圧読み取り → DS18B20 計測 → Wi-Fi 接続 → HTTP POST →
 *    DeepSleep 60秒 のサイクルを繰り返す。
 *
 *  使用モジュール:
 *    秋月電子通商「ESP-WROOM-02 DIP化キット」(AE-ESP-WROOM-02)
 *    - 技適認証あり (R 201-160606)
 *    - 書き込みは FTDI USBシリアル変換 (3.3V ロジック) で行う
 *
 *  必須配線 (詳細は「電池駆動配線ガイド.md」参照):
 *    - GPIO16 (XPD_DCDC) ─ RST    : DeepSleep からの wake 用 (必須)
 *    - DS18B20 VCC ─ 3V3 (常時給電) / DATA ─ GPIO4 / プルアップ 4.7kΩ ─ 3V3
 *    - 電池電圧検出: 電池+ ─ 330kΩ ─ A0 ─ 100kΩ ─ GND の分圧
 *    - HT7333-1 出力に 47µF 電解 (Wi-Fi 通信時の電力バッファ)
 *
 *  時刻について:
 *    本コードはタイムスタンプを生成・送信しない。タイムスタンプは
 *    Raspberry Pi (Flask) 側で受信時に付与する設計。
 *
 *  必要なライブラリ:
 *    - OneWire           by Jim Studt          (>=2.3.x)
 *    - DallasTemperature by Miles Burton       (>=3.9.x)
 *    - ArduinoJson       by Benoit Blanchon    (>=6.21.x, v6 系)
 *
 *  Arduino IDE ボード設定:
 *    ボード        : Generic ESP8266 Module
 *    Flash Size    : 4MB (FS:2MB OTA:~1019KB)
 *    Flash Mode    : DOUT
 *    CPU Frequency : 80 MHz
 *    Reset Method  : no dtr (aka ck)
 *    Upload Speed  : 115200
 *
 *  日付: 2026-05
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>


// ============================================================
//  ハードコード設定
// ============================================================
#define WIFI_SSID         "YOUR_AP_SSID_HERE"
#define WIFI_PASSWORD     "YOUR_AP_PASSWORD_HERE"
#define SERVER_URL        "http://192.168.4.1:5000/api/sensor"
#define DEVICE_ID         "esp8266-01"


// ============================================================
//  動作パラメータ
// ============================================================
#define WIFI_TIMEOUT_MS         5000UL
#define HTTP_TIMEOUT_MS         5000UL
#define DEEP_SLEEP_SEC          60
#define SENSOR_RESOLUTION_BITS  12


// ============================================================
//  ピン
// ============================================================
#define ONE_WIRE_BUS      4      // GPIO4: DS18B20 DATA
#define POWER_SOURCE_PIN  A0     // 電池電圧検出 (330kΩ + 100kΩ 分圧)


// ============================================================
//  オブジェクト
// ============================================================
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);


// ============================================================
//  setup() のみで処理。loop() には戻らない (DeepSleep)
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.println();
  Serial.println("============================================");
  Serial.println("  ESP-WROOM-02 + DS18B20  電池駆動 DeepSleep 版");
  Serial.println("============================================");

  // ===== 1. 電源電圧読み取り =====
  // 330kΩ (上) + 100kΩ (下) の分圧を A0 (TOUT, ADC 0~1.0V) で読む。
  // 元電圧 = A0電圧 × (330+100)/100 = A0電圧 × 4.3
  // よって、ADC 0..1023 を 0..4.3V にマッピングする。
  int adcValue = analogRead(POWER_SOURCE_PIN);
  float voltage = (adcValue / 1023.0) * 4.3;
  bool isBatteryMode = (voltage < 2.5);

  // 電池残量を計算 (2.5V=0%, 3.3V=100%)
  // ※HT7333-1 の動作下限が 3.3V 付近、ドロップアウト境界が 2.5V 付近
  float batteryPercent = ((voltage - 2.5) / 0.8) * 100.0;
  if (batteryPercent < 0.0) batteryPercent = 0.0;
  if (batteryPercent > 100.0) batteryPercent = 100.0;

  Serial.printf("[POWER] adc=%d voltage=%.2fV battery=%.1f%% battery_mode=%s\n",
                adcValue, voltage, batteryPercent,
                isBatteryMode ? "true" : "false");

  // ===== 2. DS18B20 初期化 + warm-up convert =====
  sensors.begin();
  int deviceCount = sensors.getDeviceCount();
  Serial.printf("[DS18B20] detected=%d\n", deviceCount);

  if (deviceCount > 0) {
    sensors.setResolution(SENSOR_RESOLUTION_BITS);
    // スクラッチパッド初期値 (85.00℃) を上書きするためのダミー変換
    sensors.requestTemperatures();
  } else {
    Serial.println("[WARN] DS18B20 not detected. Check wiring / pull-up.");
  }

  // ===== 3. Wi-Fi 接続 (タイムアウト 5秒) =====
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[WiFi] connecting to \"%s\" ", WIFI_SSID);

  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < WIFI_TIMEOUT_MS) {
    delay(100);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] connection failed (timeout) -> sleeping");
    goToSleep();
    return;  // 到達しない
  }
  Serial.printf("[WiFi] connected ip=%s rssi=%d dBm\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());

  // ===== 4. 本番計測 =====
  if (deviceCount > 0) {
    sensors.requestTemperatures();
  }

  // ===== 5. JSON ペイロード構築 =====
  StaticJsonDocument<1024> doc;
  doc["device_id"]       = DEVICE_ID;
  doc["voltage"]         = roundTo2Decimal(voltage);
  doc["battery_percent"] = roundTo2Decimal(batteryPercent);
  doc["is_battery_mode"] = isBatteryMode;
  doc["rssi_dbm"]        = WiFi.RSSI();

  JsonArray arr = doc.createNestedArray("sensors");
  for (int i = 0; i < deviceCount; i++) {
    JsonObject s = arr.createNestedObject();
    s["index"] = i;

    DeviceAddress addr;
    if (sensors.getAddress(addr, i)) {
      char hex[17];
      for (int j = 0; j < 8; j++) {
        sprintf(&hex[j * 2], "%02X", addr[j]);
      }
      hex[16] = '\0';
      s["address"] = hex;
    } else {
      s["address"] = "UNKNOWN";
    }

    float t = sensors.getTempCByIndex(i);
    if (t == DEVICE_DISCONNECTED_C) {
      s["temp_c"] = nullptr;  // 欠測
    } else {
      s["temp_c"] = roundTo2Decimal(t);
    }
  }

  String payload;
  serializeJson(doc, payload);
  Serial.print("[POST] body: ");
  Serial.println(payload);

  // ===== 6. HTTP POST =====
  sendHttpPost(payload);

  // ===== 7. DeepSleep へ =====
  goToSleep();
}


// ============================================================
//  loop() : DeepSleep ベースなので使用しない
// ============================================================
void loop() {
  // DeepSleep から復帰すると setup() から再実行されるため、
  // ここに来ることはない。
}


// ============================================================
//  HTTP POST 送信
// ============================================================
void sendHttpPost(const String& body) {
  WiFiClient client;
  HTTPClient http;

  if (!http.begin(client, SERVER_URL)) {
    Serial.println("[POST] http.begin() failed");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(HTTP_TIMEOUT_MS);

  int code = http.POST(body);

  if (code > 0) {
    Serial.printf("[POST] HTTP %d\n", code);
    String resp = http.getString();
    if (resp.length() > 0) {
      Serial.print("[POST] response: ");
      Serial.println(resp);
    }
  } else {
    Serial.printf("[POST] failed: %s\n", http.errorToString(code).c_str());
  }
  http.end();
}


// ============================================================
//  DeepSleep へ移行
//    GPIO16 を RST に物理接続しておくこと (これがないと wake しない)
// ============================================================
void goToSleep() {
  Serial.printf("[SLEEP] entering DeepSleep for %d seconds\n", DEEP_SLEEP_SEC);
  Serial.flush();  // バッファ吐き出してから寝る
  ESP.deepSleep((uint64_t)DEEP_SLEEP_SEC * 1000000ULL);
}


// ============================================================
//  小数点 2 桁に丸めるヘルパー
// ============================================================
float roundTo2Decimal(float v) {
  return roundf(v * 100.0f) / 100.0f;
}
