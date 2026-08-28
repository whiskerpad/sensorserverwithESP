/**
 * ============================================================
 *  ESP-WROOM-02 (技適対応) + DS18B20 温度センサー
 *      → DeepSleep 定期間隔で Raspberry Pi (Flask AP) へ HTTP POST
 * ============================================================
 *
 *  設計方針: 3 層分離アーキテクチャ (2026-07-30 導入)
 *    - 識別    = MAC 由来の device_id を自動生成 (per-chip 書換え不要)
 *    - IP割当  = Pi 側 dnsmasq の DHCP 予約 (WiFi.config 静的宣言は使わない)
 *    - 表示名  = Flask の nickname テーブルで管理
 *    詳細は outputs/docs/デバイス識別設計.md 参照
 *
 *  【重要】このスケッチは全チップ共通、書換え不要でコピペ書込み可能
 *    device_id は起動時に MAC から自動生成される (例: ESP-A1B2C3)
 *    IP は Pi 側 dnsmasq の予約設定で決まる
 *    人間向けの名前は Pi ダッシュボードの管理画面で nickname 設定
 *
 *  新チップ追加手順:
 *    1) Get_MAC_Address.ino で新チップの MAC を確認
 *    2) Pi 側 /etc/dnsmasq.d/wlan1.conf に dhcp-host= の 1 行追加
 *    3) このスケッチをコピペで書込む
 *    4) ダッシュボード管理画面で nickname 割当
 *
 *  必須配線:
 *    - GPIO16 (XPD_DCDC) ─ RST : DeepSleep wake 用 (必須)
 *    - DS18B20 VCC ─ 3V3 / DATA ─ GPIO4 / プルアップ 4.7kΩ ─ 3V3
 *    - 電池電圧検出: 電池+ ─ 330kΩ ─ A0 ─ 100kΩ ─ GND の分圧
 *    - HT7333-1 出力に 47µF 電解 (Wi-Fi 通信時の電力バッファ)
 *    詳細は outputs/ESP8266_BareModule_Wiring/電池駆動配線ガイド.md
 *
 *  Arduino IDE 設定:
 *    outputs/docs/Arduino_IDE_設定ガイド.md 参照。
 *    要点: Generic ESP8266 Module / Flash Size 4MB / Flash Mode DOUT /
 *          Reset Method "no dtr (aka ck)" / Upload Speed 115200
 *
 *  Flask 側エンドポイント: POST http://192.168.4.1:5000/api/temperature
 *
 *  DEEP_SLEEP_INTERVAL は運用要件で変更 (30e6=30秒、60e6=1分、120e6=2分、300e6=5分)
 *
 *  更新履歴:
 *    2026-07     初版 (静的 IP + フラット JSON 送信)
 *    2026-07-18  Serial.begin() 追加、JSON バッファ 256 → 384
 *    2026-07-30  3 層分離アーキテクチャに切替 (MAC ベース device_id、DHCP 予約)
 *                per-chip 書換えを廃止、全チップ共通スケッチに
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>

// ===== ハードウェア設定 =====
#define ONE_WIRE_BUS 4           // DS18B20 データピン
#define POWER_SOURCE_PIN A0      // 電源検出用ADCピン（TOUT - 330kΩ + 100kΩ分圧）

// ===== 運用パラメータ (必要に応じて調整、per-chip 書換えは不要) =====
// ------------------------------------------------------------
// 【測定周期の変更方法】 単位: マイクロ秒 (μs)、"e6" = ×1,000,000。値を書換えるだけ。
//   30 秒周期 →  30e6   / 60 秒 → 60e6   / 2 分 → 120e6 (現行)
//   5  分周期 → 300e6   / 10 分 → 600e6  / 30 分 → 1800e6
//   1  時間周期 → 3600e6
//   ※ ESP8266 の最大 DeepSleep は約 71 分 (4294e6 μs)。それ以上は分割必要。
// ------------------------------------------------------------
#define DEEP_SLEEP_INTERVAL 120e6  // 120秒 = 2 分 (マイクロ秒単位)

// ===== WiFi設定 (AP は Raspberry Pi、全チップ共通) =====
const char* apSSID = "YOUR_AP_SSID_HERE";
const char* apPassword = "YOUR_AP_PASSWORD_HERE";
const char* serverURL = "http://192.168.4.1:5000/api/temperature";
const int HTTP_TIMEOUT = 5000;

// ===== グローバル変数 =====
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
WiFiClient wifiClient;


void setup() {
    // ===== 0. Serial 初期化 (RF 校正時間確保と TX/RX ピン既知化) =====
    Serial.begin(115200);
    delay(100);

    // ===== 1. 起動直後の安定化 =====
    delay(500);

    // ===== 2. device_id を MAC から自動生成 =====
    // MAC 下位 3 バイト (6 hex) を device_id にする
    // 例: MAC=84:CC:A8:A1:B2:C3 → device_id="ESP-A1B2C3"
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char deviceId[16];
    snprintf(deviceId, sizeof(deviceId), "ESP-%02X%02X%02X",
             mac[3], mac[4], mac[5]);

    // ===== 3. 温度取得 =====
    sensors.begin();
    sensors.setResolution(12);
    sensors.requestTemperatures();
    delay(800);  // 12bit解像度: 750ms

    float temp = sensors.getTempCByIndex(0);

    // センサーエラーチェック
    if (temp == DEVICE_DISCONNECTED_C || temp == -127.0 || temp == 85.0) {
        temp = -999.0;
    }

    // ===== 4. 電源検出 =====
    int adcValue = analogRead(POWER_SOURCE_PIN);
    float voltage = (adcValue / 1023.0) * 4.3;
    bool isBatteryMode = (voltage < 3.5);

    // 電池残量を計算 (2.5V=0%, 3.3V=100%)
    float batteryPercent = ((voltage - 2.5) / 0.8) * 100.0;
    if (batteryPercent < 0.0) batteryPercent = 0.0;
    if (batteryPercent > 100.0) batteryPercent = 100.0;

    // ===== 5. WiFi接続 (静的 IP を MAC 下位バイトから自動生成、方式 D) =====
    // 【変更 2026-08-21】DHCP → 静的 IP に戻す (per-chip 書換え不要は維持)
    //   経緯: 2026-07-30 に DHCP 化した際「電池差は誤差レベル」と判断したが、
    //         実測で電池寿命が 1 か月+ → 2 週間強に短縮していた。
    //         DHCP DISCOVER/OFFER/REQUEST/ACK の 3-5 秒 × 720 回/日で消耗大。
    //   解決: MAC 下位バイトから IP 第 4 オクテットを導出、WiFi.config で静的宣言。
    //         per-chip 書換えは不要 (MAC は物理的にユニーク)、
    //         AP セグメント 192.168.4.0/24 の .100-.227 レンジに自動散布。
    WiFi.persistent(false);       // flash 書込み省略 (起動 30ms 短縮 + flash 摩耗防止)
    WiFi.mode(WIFI_STA);
    WiFi.setPhyMode(WIFI_PHY_MODE_11N);  // 11n 固定で接続高速化

    // MAC 下位 1 バイト → IP 第 4 オクテット (100〜227 の範囲)
    // (0x7F マスクで 128 通り、+100 で .100-.227 の 128 IP に散布)
    IPAddress fixedIP(192, 168, 4, 100 + (mac[5] & 0x7F));
    IPAddress gateway(192, 168, 4, 1);
    IPAddress subnet(255, 255, 255, 0);
    WiFi.config(fixedIP, gateway, subnet);
    delay(100);
    WiFi.begin(apSSID, apPassword);

    int attempts = 0;
    int maxAttempts = 20;  // 10秒
    while (WiFi.status() != WL_CONNECTED && attempts < maxAttempts) {
        delay(500);
        attempts++;
    }

    // ===== 6. データ送信 =====
    if (WiFi.status() == WL_CONNECTED && temp != -999.0) {

        // JSON バッファ 384 バイト (温度値桁数変動やフィールド追加への余裕)
        StaticJsonDocument<384> doc;
        doc["device_id"] = deviceId;
        doc["name"] = deviceId;                              // nickname 未設定時のフォールバック用
        doc["temperature"] = round(temp * 100) / 100.0;
        doc["temp"] = round(temp * 100) / 100.0;
        doc["ip_address"] = WiFi.localIP().toString();       // dnsmasq が割当てた実 IP
        doc["voltage"] = round(voltage * 100) / 100.0;
        doc["battery_percent"] = (int)batteryPercent;
        doc["battery_mode"] = isBatteryMode ? 1 : 0;
        doc["rssi"] = WiFi.RSSI();                            // Flask が優先読み
        doc["signal_strength"] = WiFi.RSSI();                 // レガシー互換

        String payload;
        serializeJson(doc, payload);

        // HTTP POST
        HTTPClient http;
        http.setTimeout(HTTP_TIMEOUT);
        http.begin(wifiClient, serverURL);
        http.addHeader("Content-Type", "application/json");
        int httpCode = http.POST(payload);
        http.end();
    }

    // ===== 7. Deep Sleep =====
    delay(100);
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(500);

    // GPIO16 (D0) -> RST ピン接続が必須
    ESP.deepSleep(DEEP_SLEEP_INTERVAL, WAKE_RF_DEFAULT);
}


void loop() {
    // DeepSleep 環境では使用しません
}
