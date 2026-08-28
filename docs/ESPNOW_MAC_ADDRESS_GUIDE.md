# ESP-NOW MACアドレス登録ガイド

## 📋 質問

**ESP-NOWを使用するときは親機（マスターESP32）に子機（センサーESP32C3）のMACアドレスの登録が必要か？**

---

## ✅ 答え

### 短い答え

**いいえ、親機（マスターESP32）に子機のMACアドレスを事前登録する必要はありません。**

ただし：
- ✅ **子機は親機のMACアドレスを登録する必要があります**（送信先を指定するため）
- ✅ **親機は子機のMACアドレスを事前登録しなくても受信できます**（ブロードキャストモード）

---

## 🔍 ESP-NOWの動作原理

### 現在の実装（推奨）

#### 親機（マスターESP32）側

```cpp
// ESP-NOW初期化
esp_now_init();

// 受信コールバックを登録
esp_now_register_recv_cb(on_data_recv);

// 子機のMACアドレスは登録していない
// → すべてのESP-NOWデバイスからの受信が可能
```

**特徴**:
- 子機のMACアドレスを事前登録しない
- 受信コールバックで送信元のMACアドレスを自動取得
- 複数の子機から受信可能（最大20台程度）

#### 子機（センサーESP32C3）側

```cpp
// 親機のMACアドレスを登録
uint8_t masterMAC[] = {0x2C, 0xBC, 0xBB, 0x4D, 0x99, 0xBC};

esp_now_peer_info_t peerInfo = {};
memcpy(peerInfo.peer_addr, masterMAC, 6);
peerInfo.channel = 1;
peerInfo.encrypt = false;
esp_now_add_peer(&peerInfo);  // ← 親機のMACアドレスを登録

// 送信
esp_now_send(masterMAC, (uint8_t *)&data, sizeof(data));
```

**特徴**:
- 親機のMACアドレスを事前登録する必要がある
- 送信先を指定するため

---

## 📊 登録の必要性まとめ

| デバイス | 相手のMACアドレス登録 | 理由 |
|---------|---------------------|------|
| **子機（センサー）** | ✅ **必要** | 送信先を指定するため |
| **親機（マスター）** | ❌ **不要** | 受信コールバックで自動受信可能 |

---

## 🔒 セキュリティ強化版（オプション）

親機側で子機のMACアドレスをホワイトリストとして登録することも可能です。

### 親機側のコード例（ホワイトリスト版）

```cpp
// 許可する子機のMACアドレスリスト
uint8_t allowedMACs[][6] = {
    {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0x01},  // 子機1
    {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0x02},  // 子機2
    {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0x03},  // 子機3
};

void setup() {
    // ...
    
    // ESP-NOW初期化
    esp_now_init();
    
    // 許可された子機のMACアドレスを登録
    for (int i = 0; i < 3; i++) {
        esp_now_peer_info_t peerInfo = {};
        memcpy(peerInfo.peer_addr, allowedMACs[i], 6);
        peerInfo.channel = 1;
        peerInfo.encrypt = false;
        esp_now_add_peer(&peerInfo);
    }
    
    // 受信コールバック登録
    esp_now_register_recv_cb(on_data_recv);
}

// 受信コールバック（ホワイトリストチェック）
void on_data_recv(const uint8_t *mac_addr, const uint8_t *incomingData, int len) {
    // MACアドレスが許可リストにあるかチェック
    bool isAllowed = false;
    for (int i = 0; i < 3; i++) {
        if (memcmp(mac_addr, allowedMACs[i], 6) == 0) {
            isAllowed = true;
            break;
        }
    }
    
    if (!isAllowed) {
        Serial.println("Rejected: Unknown MAC address");
        return;
    }
    
    // データ処理
    // ...
}
```

**メリット**:
- ✅ セキュリティが向上（許可されたデバイスのみ受信）
- ✅ 不正なデバイスからのデータを拒否

**デメリット**:
- ⚠️ 子機を追加するたびに親機のコードを更新する必要がある
- ⚠️ 設定が複雑になる

---

## 🎯 推奨設定

### 現在の実装（推奨）✅

**親機**: 子機のMACアドレスを登録しない（すべてのデバイスから受信可能）  
**子機**: 親機のMACアドレスを登録する

**メリット**:
- ✅ 設定が簡単
- ✅ 新しい子機を追加する際に親機のコード変更が不要
- ✅ 柔軟性が高い

**使用シーン**:
- 複数のセンサーを追加・削除する可能性がある
- セキュリティ要件が低い（同一ネットワーク内）

### セキュリティ強化版（オプション）

**親機**: 子機のMACアドレスをホワイトリストとして登録  
**子機**: 親機のMACアドレスを登録

**メリット**:
- ✅ セキュリティが向上
- ✅ 許可されたデバイスのみ受信

**使用シーン**:
- セキュリティ要件が高い
- 固定されたセンサー構成

---

## 📝 実装例

### 現在のコード（ESP32C3_Battery_Sensor_ESPNOW.ino）

```cpp
// 子機側（センサーESP32C3）
void setup() {
    // ...
    
    // 親機のMACアドレスを登録 ← 必要
    uint8_t masterMAC[] = {0x2C, 0xBC, 0xBB, 0x4D, 0x99, 0xBC};
    
    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, masterMAC, 6);
    peerInfo.channel = 1;
    peerInfo.encrypt = false;
    esp_now_add_peer(&peerInfo);
    
    // ...
}
```

```cpp
// 親機側（マスターESP32）
void setup() {
    // ...
    
    // ESP-NOW初期化
    esp_now_init();
    
    // 受信コールバック登録
    esp_now_register_recv_cb(on_data_recv);
    
    // 子機のMACアドレスは登録していない ← 不要
    
    // ...
}

// 受信コールバック（送信元のMACアドレスを自動取得）
void on_data_recv(const uint8_t *mac_addr, const uint8_t *incomingData, int len) {
    // mac_addr パラメータから送信元のMACアドレスを取得可能
    Serial.printf("Received from %02X:%02X:%02X:%02X:%02X:%02X\n",
        mac_addr[0], mac_addr[1], mac_addr[2], 
        mac_addr[3], mac_addr[4], mac_addr[5]);
    
    // データ処理
    // ...
}
```

---

## 🔗 関連ドキュメント

- `ESP_NOW_IMPLEMENTATION.md`: ESP-NOW実装の詳細
- `ESP32C3_Battery_Sensor_ESPNOW.ino`: ESP-NOW版のコード例

