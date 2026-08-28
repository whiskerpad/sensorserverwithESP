// sensor_data.h - マスターとセンサーの共通定義

#ifndef SENSOR_DATA_H
#define SENSOR_DATA_H

// ESP-NOWで送受信するセンサーデータ構造
// マスター ESP32 とセンサー ESP8266/ESP32 の両方で使用
typedef struct {
    char sensor_id[16];      // "ESP8266_PROT_01"など
    char sensor_name[32];    // "DS18B20-01"など
    float temp;              // 温度(℃)
    float humidity;          // 湿度(%) ※DS18B20は0で固定
    int8_t rssi;             // 信号強度(dBm)
    uint32_t timestamp;      // タイムスタンプ
} SensorData;

#endif
