# ESP8266 MAC アドレス取得

## 概要
ESP8266 の MAC アドレスを取得するシンプルなスケッチです。

## 使用方法
このコードを Arduino IDE で ESP8266 に書き込み、シリアルモニターで MAC アドレスを確認します。

## スケッチ

```cpp
#include <ESP8266WiFi.h>

void setup() {
  Serial.begin(115200);
  delay(1000);

  // ESP8266のWi-FiをSTAモードに設定
  WiFi.mode(WIFI_STA);
  // 内部的に一度接続を切断して初期化を確実にする
  WiFi.disconnect();
  delay(100);

  Serial.println("");
  Serial.println("Checking ESP8266 MAC Address...");

  // MACアドレスの取得
  String mac = WiFi.macAddress();

  Serial.print("MAC Address: ");
  Serial.println(mac);
}

void loop() {
  // 10秒ごとに再表示（確認用）
  delay(10000);
  Serial.print("Current MAC: ");
  Serial.println(WiFi.macAddress());
}
```

## 出力例
```
Checking ESP8266 MAC Address...
MAC Address: AA:BB:CC:DD:EE:FF
Current MAC: AA:BB:CC:DD:EE:FF
```

## 用途
- **センサー ESP8266**: MAC アドレスをメモして ESP-NOW の送信先アドレスとして設定

## 重要ポイント
- `WiFi.mode(WIFI_STA)` を設定して初期化
- `WiFi.disconnect()` で内部的にリセット
- シリアルモニターは 115200 baud で開く
- `loop()` で 10秒ごとに再表示（確認用）

## ESP32 との違い
| 項目 | ESP32 | ESP8266 |
|-----|-------|--------|
| ライブラリ | `<WiFi.h>` | `<ESP8266WiFi.h>` |
| MAC 取得 | `WiFi.macAddress()` | `WiFi.macAddress()` |
| 基本的な使い方 | ほぼ同じ | ほぼ同じ |
