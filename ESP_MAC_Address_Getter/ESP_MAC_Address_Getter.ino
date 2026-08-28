// ===== ESP32 MAC アドレス取得スケッチ =====
// このスケッチを ESP32 に書き込んで実行すると、
// シリアルモニターに MAC アドレスが表示されます。
// その値を他のスケッチの masterMAC[] に設定してください。

#include <WiFi.h>

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n\n=== ESP32 MAC Address Getter ===");
    
    // WiFi初期化
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    delay(100);
    
    // MAC アドレス取得
    uint8_t mac[6];
    WiFi.macAddress(mac);
    
    Serial.println("Station MAC Address:");
    Serial.printf("%02X:%02X:%02X:%02X:%02X:%02X\n\n", 
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    
    Serial.println("C/C++ 配列形式:");
    Serial.printf("uint8_t mac[] = {0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X};\n\n", 
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    
    Serial.println("このスケッチは無限ループしないため、");
    Serial.println("MACアドレスを確認したら他のスケッチに書き込んでください。");
}

void loop() {
    delay(1000);
}
