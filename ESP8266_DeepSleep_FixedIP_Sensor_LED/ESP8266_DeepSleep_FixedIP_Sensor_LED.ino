/**
 * ============================================================
 *  ESP-WROOM-02 + DS18B20 + 状態表示 LED 3 色 (現地診断版・恒久保持)
 *      → DeepSleep 定期間隔で Raspberry Pi (Flask AP) へ HTTP POST
 * ============================================================
 *
 *  設計方針: 本番版 (ESP8266_DeepSleep_FixedIP_Sensor.ino) と同じく
 *  3 層分離アーキテクチャ (2026-07-30 導入):
 *    - 識別    = MAC 由来の device_id を自動生成 (per-chip 書換え不要)
 *    - IP割当  = 方式D: MAC 末尾バイトから算出した静的 IP を WiFi.config で自己宣言
 *                192.168.4.(100 + (mac[5] & 0x7F))  → .100〜.227
 *    - 表示名  = Flask の nickname テーブル
 *
 *  位置付け: 【恒久保持の現地トラブルシューティング用バージョン】
 *    現地 (ビル管理業務先) では PC を持ち込めない or シリアルモニタが使えない
 *    状況が多く、ユニバーサル基盤の端子仕上げ品質やセンサー個体差による
 *    動作不良を、LED 3 色の光り方だけで一次切り分けできる。
 *
 *  LED 動作パターン:
 *    - 赤 (GPIO5)  フリッカ 3 秒 : センサー未検出 → POST スキップ → sleep
 *    - 黄 (GPIO12) 3 秒点灯     : WiFi 接続失敗 or HTTP POST 失敗 → sleep
 *    - 緑 (GPIO13) 200ms 点灯   : POST 成功
 *
 *  LED 配線 (LED 1 本あたり):
 *    GPIO ── 330Ω ── LED anode(+) ── LED cathode(-) ── GND
 *      GPIO5  ── 330Ω ── 赤 LED (+) ── (-) ── GND
 *      GPIO12 ── 330Ω ── 黄 LED (+) ── (-) ── GND
 *      GPIO13 ── 330Ω ── 緑 LED (+) ── (-) ── GND
 *
 *  避けた GPIO と理由:
 *    GPIO0/2/15: ブートストラップ
 *    GPIO1/3:    Serial (TX/RX)
 *    GPIO4:      DS18B20 データピン
 *    GPIO16:     DeepSleep wake の RST 直結
 *
 *  現地でよくある切り分けフロー:
 *    赤フリッカ  → DS18B20 の VCC/GND/DATA、4.7kΩ プルアップを疑う
 *    黄点灯      → AP (Pi の hostapd) 稼働、IP 衝突 (MAC 末尾 7bit 一致)、電池電圧を疑う
 *    何も光らない→ HT7333-1 3.3V 出力、GPIO16-RST 配線、電池残量を疑う
 *    緑瞬き      → 正常
 *
 *  【重要】このスケッチも全チップ共通、書換え不要でコピペ書込み可能
 *
 *  更新履歴:
 *    2026-07-18 LED 診断版 初版
 *    2026-07-30 3 層分離アーキテクチャに切替 (MAC ベース device_id)
 *    2026-09-06  DS18B20 の読み取りに再試行を 1 回追加 (readTemperature()):
 *      - -127 (CRC 失敗) / 85.0 (パワーオンリセット値) のとき、300ms 空けて
 *        sensors.begin() でバスを取り直し、もう一度だけ読む
 *      - 一過性の失敗で欠測になるのを減らすため。2 回目も駄目なら従来どおり
 *        -999 に落として送信をスキップする
 *      - 失敗時のみ起床時間が約 0.8 秒延びる。正常時の挙動は変更なし
 *      - delay(800) は動作実績を尊重してそのまま残した (requestTemperatures()
 *        は既定で変換完了までブロックするため理屈上は冗長)
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

// ===== ハードウェア設定 =====
#define ONE_WIRE_BUS 4
#define POWER_SOURCE_PIN A0

// LED ピン
#define LED_RED_PIN     5
#define LED_YELLOW_PIN  12
#define LED_GREEN_PIN   13

// LED 表示時間パラメータ
#define LED_FLICKER_INTERVAL_MS 100
#define LED_FLICKER_DURATION_MS 3000
#define LED_ERROR_DURATION_MS   3000
#define LED_SUCCESS_DURATION_MS 200

// ===== 運用パラメータ =====
// 【測定周期の変更方法】単位 μs、"e6" = ×1,000,000
//   30s→30e6 / 60s→60e6 / 2分→120e6 (現行) / 5分→300e6 / 10分→600e6 / 1時間→3600e6
//   ESP8266 最大 DeepSleep 約 71 分 (4294e6 μs)
#define DEEP_SLEEP_INTERVAL 120e6  // 120秒 = 2 分

// ===== WiFi 設定 =====
const char* apSSID = "YOUR_AP_SSID_HERE";
const char* apPassword = "YOUR_AP_PASSWORD_HERE";
const char* serverURL = "http://192.168.4.1:5000/api/temperature";
const int HTTP_TIMEOUT = 5000;

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
WiFiClient wifiClient;


// ============ LED ヘルパー ============
void allLedOff() {
    digitalWrite(LED_RED_PIN, LOW);
    digitalWrite(LED_YELLOW_PIN, LOW);
    digitalWrite(LED_GREEN_PIN, LOW);
}

void flickerRed(unsigned long durationMs) {
    unsigned long start = millis();
    bool ledState = false;
    while (millis() - start < durationMs) {
        ledState = !ledState;
        digitalWrite(LED_RED_PIN, ledState ? HIGH : LOW);
        delay(LED_FLICKER_INTERVAL_MS);
    }
    digitalWrite(LED_RED_PIN, LOW);
}

void showYellowError(unsigned long durationMs) {
    digitalWrite(LED_YELLOW_PIN, HIGH);
    delay(durationMs);
    digitalWrite(LED_YELLOW_PIN, LOW);
}

void showGreenSuccess(unsigned long durationMs) {
    digitalWrite(LED_GREEN_PIN, HIGH);
    delay(durationMs);
    digitalWrite(LED_GREEN_PIN, LOW);
}

void goToDeepSleep() {
    allLedOff();
    delay(100);
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(500);
    ESP.deepSleep(DEEP_SLEEP_INTERVAL, WAKE_RF_DEFAULT);
}


// ============================================================
//  DS18B20 を読む。一過性の失敗で欠測にしないため 1 回だけ再試行する。
//    -127 : スクラッチパッドの CRC 失敗 (断線とは限らない)
//    85.0 : パワーオンリセット値 (変換完了前に読んだ場合など)
//  どちらも再試行で復帰することがあるので、バスを取り直して読み直す。
//  本当に異常なら 2 回目も同じ値が返り、呼び出し側の判定でそのまま弾かれる。
// ============================================================
float readTemperature() {
    sensors.requestTemperatures();
    delay(800);                      // 12bit 変換待ち (従来どおり)
    float t = sensors.getTempCByIndex(0);

    if (t == DEVICE_DISCONNECTED_C || t == 85.0) {
        delay(300);
        sensors.begin();             // 1-Wire バスを取り直す
        sensors.requestTemperatures();
        delay(800);
        t = sensors.getTempCByIndex(0);
    }
    return t;
}


void setup() {
    // Serial 初期化 (TX/RX ピン既知化と RF 校正時間確保)
    Serial.begin(115200);
    delay(100);

    // LED ピン初期化 (全 OFF)
    pinMode(LED_RED_PIN, OUTPUT);
    pinMode(LED_YELLOW_PIN, OUTPUT);
    pinMode(LED_GREEN_PIN, OUTPUT);
    allLedOff();

    delay(500);

    // device_id を MAC から自動生成
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char deviceId[16];
    snprintf(deviceId, sizeof(deviceId), "ESP-%02X%02X%02X",
             mac[3], mac[4], mac[5]);

    // 温度取得
    sensors.begin();

    // センサー未検出 → 赤フリッカ → sleep
    int deviceCount = sensors.getDeviceCount();
    if (deviceCount == 0) {
        flickerRed(LED_FLICKER_DURATION_MS);
        goToDeepSleep();
        return;
    }

    sensors.setResolution(12);
    float temp = readTemperature();   // 失敗時は内部で 1 回だけ再試行

    bool sensorValueError = false;
    if (temp == DEVICE_DISCONNECTED_C || temp == -127.0 || temp == 85.0) {
        temp = -999.0;
        sensorValueError = true;
        flickerRed(1000);  // 短いフリッカ後、WiFi 試行に進む
    }

    // 電源検出
    int adcValue = analogRead(POWER_SOURCE_PIN);
    float voltage = (adcValue / 1023.0) * 4.3;
    // 「残量が少ない」の判定。第7回の XIAO 版と意味を揃えています。
    // 3.3V は運用上の判断値で、実測ではありません。電池を 1 セット
    // 使い切って、実際に止まる電圧を見てから決め直すのが確実です。
    const float BATTERY_LOW_V = 3.3;
    bool isBatteryLow = (voltage < BATTERY_LOW_V);

    // WiFi 接続 (静的 IP、方式 D: MAC 下位バイトから IP 導出)
    // 2026-08-21: DHCP → 静的 IP に戻す (電池寿命 2 週間 → 1 か月+ 復帰目的)
    WiFi.persistent(false);
    WiFi.mode(WIFI_STA);
    WiFi.setPhyMode(WIFI_PHY_MODE_11N);

    IPAddress fixedIP(192, 168, 4, 100 + (mac[5] & 0x7F));
    IPAddress gateway(192, 168, 4, 1);
    IPAddress subnet(255, 255, 255, 0);
    WiFi.config(fixedIP, gateway, subnet);
    delay(100);
    WiFi.begin(apSSID, apPassword);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        attempts++;
    }

    // WiFi 失敗 → 黄 LED → sleep
    if (WiFi.status() != WL_CONNECTED) {
        showYellowError(LED_ERROR_DURATION_MS);
        goToDeepSleep();
        return;
    }

    // センサー値エラー → 黄 → sleep (WiFi 生きているが送るデータ無し)
    if (sensorValueError) {
        showYellowError(LED_ERROR_DURATION_MS);
        goToDeepSleep();
        return;
    }

    // データ送信
    StaticJsonDocument<384> doc;
    doc["device_id"] = deviceId;
    doc["name"] = deviceId;
    doc["temperature"] = round(temp * 100) / 100.0;
    doc["temp"] = round(temp * 100) / 100.0;
    doc["ip_address"] = WiFi.localIP().toString();
    doc["voltage"] = round(voltage * 100) / 100.0;
    doc["battery_mode"] = isBatteryLow ? 1 : 0;
    doc["rssi"] = WiFi.RSSI();
    doc["signal_strength"] = WiFi.RSSI();

    String payload;
    serializeJson(doc, payload);

    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT);
    http.begin(wifiClient, serverURL);
    http.addHeader("Content-Type", "application/json");
    int httpCode = http.POST(payload);
    http.end();

    // POST 結果を LED で通知
    if (httpCode >= 200 && httpCode < 300) {
        showGreenSuccess(LED_SUCCESS_DURATION_MS);
    } else {
        showYellowError(LED_ERROR_DURATION_MS);
    }

    goToDeepSleep();
}

void loop() {}
