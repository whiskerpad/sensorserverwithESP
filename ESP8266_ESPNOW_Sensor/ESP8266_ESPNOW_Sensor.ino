/**
 * ============================================================
 *  [DEPRECATED / MISNAMED 2026-07-18]
 *
 *  このフォルダ名 "ESP8266_ESPNOW_Sensor" は誤解を招きます。
 *  実際の中身は ESP-NOW ではなく WiFi HTTP POST の DHCP 版
 *  (元プロジェクトの I:\...\esp_now_master_and_sensor\ESP8266_DeepSleep_Sensor
 *  から誤配置のまま持ち込んでしまった)。
 *
 *  ESP8266 の WiFi HTTP POST 版としては、より新しい静的 IP 版:
 *      outputs/ESP8266_DeepSleep_FixedIP_Sensor/
 *  を使ってください。
 *
 *  ESP-NOW を使いたい場合は ESP32/ESP32C3 版:
 *      outputs/ESP32_ESPNOW_Sensor/
 *      outputs/ESP32C3_ESPNOW_Battery_Sensor/
 *  を推奨します (ESP8266 で ESP-NOW を使うのは可能ですが、DeepSleep との
 *  併用でチューニングが必要で、実運用実績は ESP32 系の方が高い)。
 * ============================================================
 */

// このフォルダは削除候補です。
