/**
 * ============================================================
 *  ESP8266 + DS18B20 温度センサー → シリアルモニター出力
 * ============================================================
 *  概要:
 *    DS18B20温度センサーから1-Wire通信で温度を取得し、
 *    Arduino IDE のシリアルモニターに出力します。
 *    複数センサーの同時読み取りにも対応しています。
 *
 *  必要なライブラリ (Arduino IDE > ライブラリマネージャーでインストール):
 *    - OneWire       by Jim Studt  (バージョン 2.3.x)
 *    - DallasTemperature by Miles Burton (バージョン 3.9.x)
 *
 *  配線図:
 *    DS18B20       ESP8266
 *    -------       --------
 *    VCC   ------> 3.3V
 *    GND   ------> GND
 *    DATA  ------> GPIO4
 *                  ※4.7kΩプルアップ抵抗を VCC-DATA 間に接続
 *
 *  ボード設定 (Arduino IDE > ツール):
 *    ボード    : ESP-WROOM-02 DIP化キット
 *    CPU周波数  : 80MHz
 *    Flash Size : 4MB
 *    Upload Speed: 115200
 *
 *  作者: IoTプロジェクト記録用
 *  日付: 2026-05
 * ============================================================
 */

#include <OneWire.h>
#include <DallasTemperature.h>

// ── ピン設定 ──────────────────────────────────────────
//  GPIO 番号を直接指定する。ボード設定が "Generic ESP8266 Module" でも
//  問題なくコンパイルできる。
#define ONE_WIRE_BUS 4   // GPIO4

// ── 読み取り間隔 ──────────────────────────────────────
#define READ_INTERVAL_MS 2000  // 2秒ごとに温度を取得

// ── OneWire・センサーオブジェクト生成 ─────────────────
OneWire oneWire(ONE_WIRE_BUS);

DallasTemperature sensors(&oneWire);

// ── グローバル変数 ────────────────────────────────────
unsigned long lastReadTime = 0;
int deviceCount = 0;


// ============================================================
//  setup() : 起動時に1回だけ実行
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(100);

  Serial.println();
  Serial.println("============================================");
  Serial.println("  ESP8266 + DS18B20 温度モニター 起動");
  Serial.println("============================================");

  // センサーライブラリの初期化
  sensors.begin();

  // バス上のDS18B20デバイス数を確認
  deviceCount = sensors.getDeviceCount();
  Serial.print("[INFO] 検出されたDS18B20の数: ");
  Serial.println(deviceCount);

  if (deviceCount == 0) {
    Serial.println("[WARNING] センサーが見つかりません。配線を確認してください。");
    Serial.println("  - DATAピンの接続先: GPIO4");
    Serial.println("  - 4.7kΩのプルアップ抵抗が VCC-DATA 間にあるか確認");
  }

  // 各センサーのアドレス（個体識別用64bitROM）を表示
  for (int i = 0; i < deviceCount; i++) {
    DeviceAddress addr;
    if (sensors.getAddress(addr, i)) {
      Serial.print("[INFO] センサー[");
      Serial.print(i);
      Serial.print("] アドレス: ");
      printAddress(addr);
      Serial.println();
    }
  }

  Serial.println("--------------------------------------------");
  Serial.println("  計測開始 (単位: ℃)");
  Serial.println("--------------------------------------------");
}


// ============================================================
//  loop() : 繰り返し実行
// ============================================================
void loop() {
  unsigned long now = millis();

  // READ_INTERVAL_MS ごとに温度を取得して出力
  if (now - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = now;

    // 全センサーに変換コマンドを送信（非ブロッキングも可能だが今回は同期）
    sensors.requestTemperatures();

    // タイムスタンプ（起動からの経過秒）
    unsigned long elapsedSec = now / 1000;

    for (int i = 0; i < deviceCount; i++) {
      float tempC = sensors.getTempCByIndex(i);

      // エラー値チェック (-127 はセンサー未応答)
      if (tempC == DEVICE_DISCONNECTED_C) {
        Serial.print("[ERROR] センサー[");
        Serial.print(i);
        Serial.println("] 読み取りエラー (接続を確認してください)");
        continue;
      }

      // ── シリアルモニター出力 ──
      // フォーマット: [経過秒s] センサー[N]: XX.XX ℃
      Serial.print("[");
      Serial.print(elapsedSec);
      Serial.print("s] センサー[");
      Serial.print(i);
      Serial.print("]: ");
      Serial.print(tempC, 2);   // 小数点2桁
      Serial.println(" ℃");
    }

    // センサーが複数ある場合は区切り線を表示
    if (deviceCount > 1) {
      Serial.println("  ---");
    }
  }
}


// ============================================================
//  printAddress() : DeviceAddressを16進数で表示するヘルパー関数
// ============================================================
void printAddress(DeviceAddress deviceAddress) {
  for (uint8_t i = 0; i < 8; i++) {
    if (deviceAddress[i] < 0x10) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
    if (i < 7) Serial.print(":");
  }
}
