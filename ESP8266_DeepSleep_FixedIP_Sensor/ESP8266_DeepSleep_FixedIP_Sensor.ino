/**
 * ============================================================
 *  ESP-WROOM-02 (技適対応) + DS18B20 温度センサー
 *      → DeepSleep 定期間隔で Raspberry Pi (Flask AP) へ HTTP POST
 * ============================================================
 *
 *  設計方針: 3 層分離アーキテクチャ (2026-07-30 導入)
 *    - 識別    = MAC 由来の device_id を自動生成 (per-chip 書換え不要)
 *    - IP割当  = 方式D: MAC 末尾バイトから算出した静的 IP を WiFi.config で自己宣言
 *                192.168.4.(100 + (mac[5] & 0x7F))  → .100〜.227
 *                Pi 側 dnsmasq に予約は書かない (DHCP プールは .228-.254 の一時接続用)
 *    - 表示名  = Flask の nickname テーブルで管理
 *    詳細は outputs/docs/デバイス識別設計.md 参照
 *
 *  【重要】このスケッチは全チップ共通、書換え不要でコピペ書込み可能
 *    device_id は起動時に MAC から自動生成される (例: ESP-A1B2C3)
 *    IP も MAC から自動算出される (Pi 側の設定作業は不要)
 *    人間向けの名前は Pi ダッシュボードの管理画面で nickname 設定
 *
 *  新チップ追加手順:
 *    1) このスケッチをコピペで書込む (Pi 側の作業なし)
 *    2) ダッシュボード管理画面で nickname 割当
 *    ※ IP は MAC 末尾 7bit 由来なので、稀に既存機と衝突しうる。
 *       導入時に Flask の device 一覧で ip_address の重複がないか確認すること
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
 *    2026-08-21  ネットワーク層を方式D (MAC 由来の静的 IP) へ変更。
 *                実測で電池寿命が 1 か月+ → 2 週間強に半減したため DHCP を廃止
 *                per-chip 書換えを廃止、全チップ共通スケッチに
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

    float temp = readTemperature();   // 失敗時は内部で 1 回だけ再試行

    // センサーエラーチェック (再試行しても駄目なら欠測扱い)
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
        doc["ip_address"] = WiFi.localIP().toString();       // 自己宣言した実 IP
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
