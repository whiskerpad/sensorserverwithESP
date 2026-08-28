/**
 * ============================================================
 *  XIAO ESP32C3 Battery-powered Sensor (ESP-NOW 送信版)
 *
 *  ベース: I:\...\esp_now_master_and_sensor\ESP32C3_Battery_Sensor\
 *          ESP32C3_Battery_Sensor_ESPNOW_Production\ (稼働実績あり、現地展開済)
 *
 *  修正 (2026-07-30):
 *    - sensor_id を MAC 由来の "NOW-XXXXXX" 形式に自動生成
 *      → WiFi 直接 POST 系 (ESP-XXXXXX) と区別できる命名
 *      → per-chip 書換え不要
 *    - SENSOR_ID ハードコード ("NOW_BAT_02") 廃止
 *    - SENSOR_NAME は "DS18B20-NOW-Bat" 汎用名に (nickname テーブルで個別化)
 *
 *  【変更しなかった項目 (稼働実績を尊重)】:
 *    - DS18B20 = GPIO4 (D2)   XIAO ESP32-C3 は GPIO0 が外部未引出しのため GPIO4 を採用
 *                              (2026-08-16 検討: WiFi 版と統一、無印 ESP32 でも共通利用可)
 *    - バッテリー ADC = A1 (GPIO3、270kΩ 1:1 分圧、LiPo 3.7V)
 *    - analogReadMilliVolts + 16 サンプル平均
 *    - LiPo 低下閾値 3.0V
 *    - SEND_INTERVAL 300 秒、DeepSleep
 *    - DEBUG_MODE フラグ
 * ============================================================
 */

#include <esp_now.h>
#include <WiFi.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// ===== 設定 =====
#define ONE_WIRE_BUS 4        // DS18B20 データピン (GPIO4 = D2、XIAO/無印 ESP32 共通で使える)
#define BATTERY_ADC_PIN A1    // バッテリー監視 (A1/GPIO3に変更 - GPIO2/A0はストラッピングピンのため回避)
#define SENSOR_NAME "DS18B20-NOW-Bat"  // nickname 未設定時のフォールバック
// ------------------------------------------------------------
// 【測定周期の変更方法】 単位: 秒。値を書換えるだけ (loop 内で ×1e6 して μs に変換)
//   30 秒周期 → 30 / 60 秒 → 60 / 5 分 → 300 (現行) / 10 分 → 600 / 30 分 → 1800 / 1 時間 → 3600
//   周期を長くすると電池寿命が伸びる。ESP-NOW は通信 ~0.2 秒 + 温度取得 ~1 秒 なので、
//   短周期 (30 秒) でも WiFi 版よりずっと電池持ちが良い。
// ------------------------------------------------------------
#define SEND_INTERVAL 300      // 300秒 = 5 分ごとに送信 (電池駆動、秒単位)
#define DEBUG_MODE false       // デバッグモード（Deep Sleepを無効化してテスト）

// マスター ESP32 の MAC アドレス (Master 起動時の Serial モニタで確認、書換え可)
uint8_t masterMAC[] = {0x2C, 0xBC, 0xBB, 0x4D, 0x99, 0xBC};

// MAC 由来 sensor_id (setup 内で生成、"NOW-XXXXXX" 形式)
char sensor_id[16];

// センサーデータ構造
typedef struct {
    char sensor_id[16];
    char sensor_name[32];
    float temp;
    float humidity;
    int8_t rssi;
    uint32_t timestamp;
    float battery_voltage;
    bool battery_mode;
} SensorData;

// OneWire と DallasTemperature インスタンス
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// ===== バッテリー検出関数 =====
// XIAO ESP32C3用 - 分圧回路対応（BAT+ -> R1(270k) -> A1 -> R2(270k) -> GND）
// 注意: A0（GPIO2）はストラッピングピンのため使用不可
// A1（GPIO3）を使用することで、プログラム書き込み時の問題を回避
float getBatteryVoltage() {
    // 自動キャリブレーション対応（analogReadMilliVolts使用）
    uint32_t sumVoltage = 0;
    
    // 16回読み込んで平均化（ノイズ除去）
    for (int i = 0; i < 16; i++) {
        // A1（GPIO3）を使用 - GPIO2/A0はストラッピングピンのため回避
        sumVoltage += analogReadMilliVolts(BATTERY_ADC_PIN);
        delayMicroseconds(50);
    }
    
    // 平均値を計算
    float averageMilliV = sumVoltage / 16.0;
    
    // 分圧回路（1:1分圧）の補正：2倍にする
    float batteryVoltage = (averageMilliV / 1000.0) * 2.0;
    
    return batteryVoltage;
}

// バッテリーモード判定（低下検出）
bool isBatteryLow(float voltage) {
    // 18650: 3.0V未満で低下と判定
    return voltage < 3.0;
}

// ESP-NOW送信コールバック
void on_data_sent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
    Serial.print("[CALLBACK] ESP-NOW Send Status: ");
    if (status == ESP_NOW_SEND_SUCCESS) {
        Serial.println("SUCCESS");
    } else {
        Serial.print("FAILED (status code: ");
        Serial.print(status);
        Serial.println(")");
    }
}

void setup() {
    // シリアル初期化（即座に開始）
    Serial.begin(115200);
    
    // 最初の出力を即座に試みる（デバッグ用）
    Serial.println("\n\n");
    Serial.println("=== STARTUP ===");
    delay(500);  // シリアルポートが確立されるまで待機
    
    // Deep Sleep復帰理由を表示
    esp_sleep_wakeup_cause_t wakeup_reason = esp_sleep_get_wakeup_cause();
    Serial.print("Wakeup reason: ");
    switch(wakeup_reason) {
        case ESP_SLEEP_WAKEUP_EXT0:
            Serial.println("External signal using RTC_IO");
            break;
        case ESP_SLEEP_WAKEUP_EXT1:
            Serial.println("External signal using RTC_CNTL");
            break;
        case ESP_SLEEP_WAKEUP_TIMER:
            Serial.println("Timer");
            break;
        case ESP_SLEEP_WAKEUP_TOUCHPAD:
            Serial.println("Touchpad");
            break;
        case ESP_SLEEP_WAKEUP_ULP:
            Serial.println("ULP program");
            break;
        default:
            Serial.println("Power on reset or first boot");
            break;
    }
    
    Serial.println("\n=== XIAO ESP32C3 Sensor with Battery (DS18B20) - ESP-NOW ===");
    Serial.println("sensor_id (MAC-based): " + String(sensor_id));
    Serial.println("Sensor Name (fallback): " + String(SENSOR_NAME));
    Serial.println("Mode: Battery Powered (1min interval)");
    Serial.println("Communication: ESP-NOW");
    Serial.println("DS18B20 Pin: GPIO" + String(ONE_WIRE_BUS));
    Serial.println("Battery ADC Pin: A1 (GPIO3)");
    Serial.print("DEBUG_MODE: ");
    Serial.println(DEBUG_MODE ? "ON (Deep Sleep disabled)" : "OFF");
    
    // DS18B20初期化（WiFi初期化の前に行う - 動作確認済みの方法）
    Serial.println("\n--- DS18B20 Detection ---");
    sensors.begin();
    delay(100);  // 初期化待機（動作確認済みコードと同じ）
    
    int deviceCount = sensors.getDeviceCount();
    Serial.print("DS18B20 Found: ");
    Serial.println(deviceCount);
    
    if (deviceCount == 0) {
        Serial.println("ERROR: No DS18B20 sensor found!");
        Serial.println("Check wiring and power supply");
        Serial.println("Wiring:");
        Serial.println("  - DS18B20 DATA → GPIO4 (D2)");
        Serial.println("  - DS18B20 VCC → 3.3V");
        Serial.println("  - DS18B20 GND → GND");
        Serial.println("  - 4.7kΩ pullup resistor between DATA and VCC");
        delay(5000);
        if (!DEBUG_MODE) {
            goToDeepSleep();
        } else {
            Serial.println("DEBUG_MODE: Continuing despite error...");
        }
    } else {
        Serial.println("✅ DS18B20 sensor detected successfully!");
    }
    
    // バッテリー電圧表示
    float battVoltage = getBatteryVoltage();
    bool battLow = isBatteryLow(battVoltage);
    Serial.printf("Battery Voltage: %.2fV\n", battVoltage);
    Serial.printf("Battery Status: %s\n", battLow ? "⚠️ LOW" : "🔋 GOOD");
    
    Serial.flush();  // シリアル出力を確実に送信
    
    // WiFi初期化（ESP-NOWに必須、MAC 読取りにも必要）
    Serial.println("\n--- WiFi/ESP-NOW Initialization ---");
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);

    // MAC 由来 sensor_id を生成 ("NOW-XXXXXX")
    uint8_t mac[6] = {0};
    WiFi.macAddress(mac);
    snprintf(sensor_id, sizeof(sensor_id), "NOW-%02X%02X%02X",
             mac[3], mac[4], mac[5]);
    Serial.printf("ESP32C3 MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    Serial.printf("sensor_id auto-generated: %s\n", sensor_id);
    
    // ESP-NOW初期化
    Serial.println("Initializing ESP-NOW...");
    esp_err_t init_result = esp_now_init();
    if (init_result != ESP_OK) {
        Serial.print("ERROR: ESP-NOW initialization failed: ");
        Serial.println(init_result);
        Serial.println("Retrying in 2 seconds...");
        delay(2000);
        // 再試行
        init_result = esp_now_init();
        if (init_result != ESP_OK) {
            Serial.println("ERROR: ESP-NOW initialization failed again!");
            Serial.println("Will continue anyway for debugging...");
        } else {
            Serial.println("ESP-NOW initialized successfully on retry");
        }
    } else {
        Serial.println("ESP-NOW initialized successfully");
    }
    
    // コールバック登録
    Serial.println("Registering send callback...");
    esp_now_register_send_cb(on_data_sent);
    
    // ピア登録（マスター ESP32）
    Serial.print("Adding peer (MAC: ");
    for(int i = 0; i < 6; i++) {
        if(i > 0) Serial.print(":");
        Serial.print(masterMAC[i], HEX);
    }
    Serial.println(")...");
    
    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, masterMAC, 6);
    peerInfo.channel = 1;
    peerInfo.encrypt = false;
    esp_err_t peer_result = esp_now_add_peer(&peerInfo);
    if (peer_result != ESP_OK) {
        Serial.print("ERROR: Failed to add peer: ");
        Serial.println(peer_result);
        Serial.println("Will continue anyway for debugging...");
    } else {
        Serial.println("Master ESP32 registered successfully");
    }
    
    Serial.println("Status: Ready to send sensor data\n");
}

void loop() {
    Serial.println("\n--- Loop Start ---");
    Serial.flush();  // シリアル出力を確実に送信
    
    // DS18B20 から温度を読み込み（動作確認済みコードと同じ方法）
    // WiFi初期化後でも動作するように、sensors.begin()を再実行
    sensors.begin();
    delay(50);
    
    sensors.requestTemperatures();
    delay(100);  // 変換完了待機（動作確認済みコードと同じ）
    
    float temp = sensors.getTempCByIndex(0);
    
    // エラーチェック
    if (temp == DEVICE_DISCONNECTED_C) {
        Serial.println("ERROR: DS18B20 disconnected or not responding");
        Serial.print("  Temperature value: ");
        Serial.println(temp, 2);
        
        // 再初期化を試みる
        Serial.println("Attempting to reinitialize DS18B20...");
        sensors.begin();
        delay(200);
        sensors.requestTemperatures();
        delay(200);
        temp = sensors.getTempCByIndex(0);
        
        if (temp == DEVICE_DISCONNECTED_C) {
            Serial.println("ERROR: Still not responding after reinit");
            if (!DEBUG_MODE) {
                goToDeepSleep();
            } else {
                Serial.println("DEBUG_MODE: Waiting 5 seconds before retry...");
                delay(5000);
            }
            return;
        } else {
            Serial.println("✅ Reinitialization successful!");
        }
    }
    
    Serial.printf("Temperature: %.2f°C\n", temp);
    
    // ESP-NOWで送信
    Serial.println("Sending data via ESP-NOW...");
    sendDataViaESPNOW(temp);
    
    // 送信完了を待つ（デバッグ用）
    delay(500);
    
    // Deep Sleep へ（60秒）
    if (DEBUG_MODE) {
        Serial.println("DEBUG_MODE: Deep Sleep disabled, waiting 10 seconds...");
        delay(10000);
    } else {
        goToDeepSleep();
    }
}

// ESP-NOW経由で送信（低電力、WiFi接続不要）
void sendDataViaESPNOW(float temperature) {
    Serial.println("Preparing sensor data...");
    
    // センサーデータ構造体を作成
    SensorData sensor_data;
    strncpy(sensor_data.sensor_id, sensor_id, sizeof(sensor_data.sensor_id) - 1);
    sensor_data.sensor_id[sizeof(sensor_data.sensor_id) - 1] = '\0';
    strncpy(sensor_data.sensor_name, SENSOR_NAME, sizeof(sensor_data.sensor_name) - 1);
    sensor_data.sensor_name[sizeof(sensor_data.sensor_name) - 1] = '\0';
    sensor_data.temp = temperature;
    sensor_data.humidity = 0.0;  // DS18B20 は湿度を測定しないので 0
    sensor_data.rssi = WiFi.RSSI();
    sensor_data.timestamp = millis();
    sensor_data.battery_voltage = getBatteryVoltage();
    sensor_data.battery_mode = isBatteryLow(sensor_data.battery_voltage);
    
    Serial.printf("Data prepared - Temp: %.2f°C, Battery: %.2fV\n", 
                  sensor_data.temp, sensor_data.battery_voltage);
    Serial.printf("Data size: %d bytes\n", sizeof(sensor_data));
    
    // 送信
    Serial.println("Calling esp_now_send()...");
    esp_err_t result = esp_now_send(masterMAC, (uint8_t *)&sensor_data, sizeof(sensor_data));
    
    if (result == ESP_OK) {
        Serial.println("esp_now_send() returned ESP_OK (callback will show actual status)");
    } else {
        Serial.print("ERROR: esp_now_send() failed with code: ");
        Serial.println(result);
    }
}

// Deep Sleep へ移行（60秒間スリープ）
void goToDeepSleep() {
    Serial.printf("Going to Deep Sleep for %d seconds...\n", SEND_INTERVAL);
    Serial.flush();
    
    // 60秒 = 60,000,000マイクロ秒
    esp_sleep_enable_timer_wakeup(SEND_INTERVAL * 1000000);
    
    // Deep Sleep に入る
    esp_deep_sleep_start();
}

