# 🏗️ システムアーキテクチャ詳細

## 全体構成図

```
【IoT センサー層】
    ESP32
    ├─ DS18B20 温度センサー
    └─ WiFi モジュール (202.11b/g/n)
        └─ AP 接続: YOUR_AP_SSID_HERE
        └─ IP: 192.168.4.185 (DHCP 割り当て)

        HTTP POST ↓
        ↓
        ↓ /api/temperature
        ↓

【ネットワーク層】
         192.168.4.0/24 ネットワーク
    ┌─────────────────────────────────┐
    │   Raspberry Pi 4                │
    │                                 │
    │  ┌─────────────────────────┐    │
    │  │ wlan1 (USB WiFi)        │    │
    │  │ AP Mode                 │    │
    │  │ IP: 192.168.4.1         │    │
    │  │ SSID: RaspberryPi_Temp  │    │
    │  │ Role: Access Point      │    │
    │  └─────────────────────────┘    │
    │                                 │
    │  ┌─────────────────────────┐    │
    │  │ wlan0 (onboard WiFi)    │    │
    │  │ Station Mode            │    │
    │  │ IP: 192.168.11.57       │    │
    │  │ Role: Internet Client   │    │
    │  └─────────────────────────┘    │
    └─────────────────────────────────┘
        ↓
        ↓ localhost:5000
        ↓

【アプリケーション層】
    ┌─────────────────────────────────┐
    │   Flask Web Server              │
    ├─────────────────────────────────┤
    │ Core Components:                │
    │ • HTTP Listener (0.0.0.0:5000)  │
    │ • WSGI Application              │
    │ • Request Router                │
    └─────────────────────────────────┘
        ↓
    ┌─────────────────────────────────┐
    │   API Routes (REST)             │
    ├─────────────────────────────────┤
    │ POST /api/temperature           │
    │ GET  /api/sensors               │
    │ GET  /api/status                │
    │ GET  / (Dashboard HTML)         │
    └─────────────────────────────────┘
        ↓
        ↓

【データ層】
    ┌─────────────────────────────────┐
    │   SQLite Database               │
    │   temperature_data.db           │
    ├─────────────────────────────────┤
    │ Table: temperatures             │
    │ ├─ id (PRIMARY KEY)             │
    │ ├─ device_id                    │
    │ ├─ name                         │
    │ ├─ location                     │
    │ ├─ temperature                  │
    │ └─ timestamp                    │
    └─────────────────────────────────┘
        ↓
    ┌─────────────────────────────────┐
    │   Web UI (Frontend)             │
    │   dashboard.html                │
    ├─────────────────────────────────┤
    │ • Real-time Graph               │
    │ • Data Table                    │
    │ • System Status                 │
    │ • WebSocket Updates (optional)  │
    └─────────────────────────────────┘
```

---

## 📡 ネットワークフロー

### 1. **データ送信フロー（ESP32 → Raspberry Pi）**

```
[ESP32] 
  ↓
  ├─ Wi-Fi接続確認
  ├─ JSON ペイロード生成
  │  {
  │    "device_id": "ESP32_01",
  │    "name": "プロトタイプ01",
  │    "location": "設定なし",
  │    "temperature": 23.5
  │  }
  ├─ HTTP POST リクエスト構築
  │  POST /api/temperature HTTP/1.1
  │  Host: 192.168.4.1:5000
  │  Content-Type: application/json
  │  Content-Length: 95
  │
  │  [JSON Payload]
  ├─ ネットワークスタック経由で送信
  │  WiFi (802.11g) → Ethernet (AP: wlan1)
  ├─ TCP ハンドシェイク (3-way handshake)
  │  SYN → SYN-ACK → ACK
  ├─ HTTP リクエスト送信
  │  
  ↓ 192.168.4.0/24 ネットワーク
  
[Raspberry Pi - wlan1]
  ├─ ファイアウォール (ACCEPT)
  ├─ iptables ルーティング
  ├─ Flask WSGI サーバーに到達
  │
  ↓ Flask Application
  
[Flask]
  ├─ ルーティング: POST /api/temperature マッチ
  ├─ リクエスト解析
  │  ├─ JSON デコード
  │  ├─ バリデーション
  │  └─ 型変換
  ├─ API ハンドラー実行
  │  └─ /app/routes/api.py
  ├─ データベース操作
  │  └─ INSERT INTO temperatures ...
  ├─ レスポンス生成
  │  {
  │    "status": "success",
  │    "message": "Data received and stored",
  │    "temperature": 23.5,
  │    "timestamp": "2025-12-24T06:07:06.742395"
  │  }
  ├─ HTTP ステータス: 201 (Created)
  │
  ↓
  
[ESP32]
  ├─ HTTP レスポンス受信
  ├─ ステータスコード確認 (201)
  ├─ スリープモード突入（30秒待機）
  └─ 次回の送信予定時刻をセット
```

---

### 2. **Web UI 表示フロー（ブラウザ → Raspberry Pi）**

```
[ブラウザ] (192.168.11.4)
  ↓
  GET http://192.168.11.57:5000/ HTTP/1.1
  
  ↓ wlan0 ネットワーク (192.168.11.x)
  
[Raspberry Pi - wlan0]
  ├─ ファイアウォール (ACCEPT)
  ├─ Flask WSGI サーバーに到達
  
  ↓
  
[Flask - Dashboard Route]
  ├─ templates/dashboard.html をレンダリング
  ├─ HTML + CSS + JavaScript を返却
  │  └─ JavaScript が定期的に /api/sensors をポーリング
  
  ↓
  
[ブラウザ - JavaScript]
  ├─ fetch('/api/sensors') 実行
  ├─ 10秒ごとに API 呼び出し
  │
  ├─ JSON レスポンス受信：
  │  [
  │    {
  │      "device_id": "ESP32_01",
  │      "temperature": 23.5,
  │      "timestamp": "2025-12-24T06:07:06"
  │    }
  │  ]
  │
  ├─ DOM 操作で画面更新
  │  ├─ テーブル行の更新
  │  ├─ グラフのプロット
  │  └─ ステータス表示
  │
  └─ リアルタイムデータ表示完成
```

---

## 🔄 バックグラウンドタスク

### BackgroundTaskManager の役割

```python
# services/background_tasks.py

class BackgroundTaskManager:
    def start(self):
        # 3つのデーモンスレッドを起動
        
        1. start_memory_monitor()
           └─ 300秒ごとにメモリ使用率を確認
              ├─ 80% 以上 → キャッシュクリア警告
              └─ psutil で監視
        
        2. start_wifi_health_check()
           └─ 600秒ごとに WiFi の健全性を確認
              ├─ iw コマンドで信号強度取得
              ├─ AP が正常に動作しているか確認
              ├─ Station が接続されているか確認
              └─ ⚠️ 異常検出時は systemctl で再起動
        
        3. start_log_cleanup()
           └─ 86400秒(24h)ごとに古いログを削除
              └─ LOG_RETENTION_DAYS (デフォルト7日) より古いログを削除
```

**注意：** health check による自動再起動は、正しい判定ができなければ逆効果になります。
→ [LESSONS_LEARNED.md#health-check-issue](../docs/LESSONS_LEARNED.md)

---

## 🛠️ コアコンポーネント詳細

### 1. WiFiManager (`services/wifi_manager.py`)

```python
class WiFiManager:
    """WiFi ネットワーク管理
    
    責務：
    - AP モード (wlan1) の設定・起動・停止
    - Station モード (wlan0) での WiFi スキャン・接続
    - ネットワークヘルスチェック
    - IP アドレス・シグナル強度の取得
    """
    
    def setup_ap(self):
        """AP モードのセットアップ
        1. wlan1 インターフェース UP
        2. IP アドレス設定 (192.168.4.1/24)
        3. dhcpcd 設定
        4. hostapd 設定（SSID, パスワード）
        5. dnsmasq 設定（DHCP）
        6. iptables 設定（NAT）
        """
    
    def get_network_info(interface: str) -> NetworkInfo:
        """ネットワーク情報取得
        実行コマンド：
        - ip addr show <interface>    ← IP アドレス取得
        - iw <interface> link         ← SSID・シグナル強度取得
        
        ⚠️ 注意：フルパス '/usr/sbin/iw' を使用すること
        PATHが限定されるサービス環境では 'iw' だけでは見つからない
        """
    
    def health_check() -> Dict:
        """WiFi システムの健全性確認
        チェック項目：
        1. AP (wlan1) が RUNNING 状態か
        2. Station (wlan0) が接続状態か
        
        問題検出時の動作：
        - AP 停止 → systemctl stop hostapd/dnsmasq
        - 再起動 → systemctl start hostapd/dnsmasq
        """
```

### 2. Flask App (`app/__init__.py` + `app/flask_app.py`)

```python
def create_app():
    """Flask アプリケーションファクトリー
    
    機能：
    - Blueprint ロード（API, Dashboard, WiFi管理）
    - CORS 有効化
    - エラーハンドラー登録
    - ロギング設定
    
    デフォルト設定：
    - ホスト: 0.0.0.0 (全インターフェース)
    - ポート: 5000
    - デバッグ: False (本番)
    """
```

### 3. API エンドポイント (`app/routes/api.py`)

```
POST /api/temperature
  ├─ リクエストボディ: JSON
  │  {
  │    "device_id": "ESP32_01",
  │    "name": "デバイス名",
  │    "location": "場所",
  │    "temperature": 23.5
  │  }
  ├─ バリデーション: device_id と temperature は必須
  ├─ DB 操作: INSERT
  └─ レスポンス: 201 Created

GET /api/sensors
  ├─ 最新の温度データを全デバイス分取得
  ├─ JSON 配列で返却
  └─ レスポンス: 200 OK

GET /api/status
  ├─ システム全体の状態
  ├─ WiFi ステータス (AP, Station)
  ├─ アップタイム
  └─ レスポンス: 200 OK
```

### 4. データベーススキーマ (`database/models.py`)

```sql
CREATE TABLE temperatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,           -- "ESP32_01"
    sensor_id TEXT,                     -- "温度センサー1"
    name TEXT NOT NULL,                 -- "プロトタイプ01"
    location TEXT,                      -- "リビング"
    temperature REAL NOT NULL,          -- 23.5
    humidity REAL,                      -- (オプション) 65.2
    pressure REAL,                      -- (オプション) 1013.25
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_device_id_timestamp 
ON temperatures(device_id, timestamp DESC);
```

---

## 🔐 ネットワークセキュリティ設定

### iptables ルール

```bash
# AP → Station への通信許可 (ESP32 → インターネット経由)
sudo iptables -A FORWARD \
  -i wlan1 -o wlan0 -j ACCEPT

# Station → AP の応答許可 (インターネット → ESP32)
sudo iptables -A FORWARD \
  -i wlan0 -o wlan1 \
  -m state --state RELATED,ESTABLISHED -j ACCEPT

# NAT 設定 (wlan0 経由でのマスカレード)
sudo iptables -t nat \
  -A POSTROUTING -o wlan0 -j MASQUERADE
```

---

## 📊 データフロー例：温度データの一生

```
時刻: 2025-12-24 06:07:06

┌─────────────────────────────────────────────────────────┐
│ [1] ESP32 が温度を計測                                 │
│     温度値: 23.5°C                                     │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [2] JSON ペイロード生成                                 │
│     {                                                    │
│       "device_id": "ESP32_01",                          │
│       "name": "プロトタイプ01",                         │
│       "location": "設定なし",                           │
│       "temperature": 23.5                              │
│     }                                                    │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [3] HTTP POST 送信                                      │
│     宛先: http://192.168.4.1:5000/api/temperature      │
│     ネットワーク: wlan1 (AP: YOUR_AP_SSID_HERE)  │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [4] Raspberry Pi で受信                                 │
│     インターフェース: wlan1 (192.168.4.1)              │
│     プロセス: Flask WSGI Server (PID: 12177)           │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [5] Flask でリクエスト処理                              │
│     ルート: POST /api/temperature                       │
│     ハンドラー: @api_bp.route('/temperature', ...)      │
│     バリデーション: ✓ OK                                │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [6] データベース挿入                                     │
│     SQL: INSERT INTO temperatures (...)                 │
│     テーブル: temperatures                              │
│     レコード ID: 12345 (新規生成)                       │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [7] HTTP レスポンス返却                                 │
│     ステータス: 201 Created                              │
│     ボディ: {                                            │
│       "status": "success",                              │
│       "message": "Data received and stored",            │
│       "temperature": 23.5,                              │
│       "timestamp": "2025-12-24T06:07:06.742395"        │
│     }                                                    │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [8] ESP32 がレスポンス受信                              │
│     ステータスコード確認: 201 ✓                         │
│     データは正常に保存された                             │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [9] Raspberry Pi でブラウザアクセス                     │
│     GET http://192.168.11.57:5000/                     │
│     ダッシュボード表示                                  │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ [10] JavaScript が自動ポーリング                         │
│      fetch('/api/sensors') → 最新データ取得             │
│      データベースから: SELECT * FROM temperatures ...   │
│      レコード ID 12345 がヒット                         │
│      ブラウザ画面にリアルタイム表示                     │
└─────────────────────────────────────────────────────────┘
```

---

## 📈 スケーラビリティ

### 複数 ESP32 デバイスへの対応

```
[ESP32_01]  [ESP32_02]  [ESP32_03]
     ↓          ↓           ↓
     └──────────┼───────────┘
                ↓
           AP: 192.168.4.1
         (YOUR_AP_SSID_HERE)
                ↓
    ┌───────────────────────────┐
    │   Flask Server (1 つ)      │
    │   /api/temperature        │
    │   ↓                        │
    │   device_id で識別        │
    │   ↓                        │
    │  SQLite DB                │
    │   ├─ ESP32_01 のレコード  │
    │   ├─ ESP32_02 のレコード  │
    │   └─ ESP32_03 のレコード  │
    └───────────────────────────┘
                ↓
            Web UI
         (全デバイスの
          データを表示)
```

---

**最後に更新**: 2025年12月24日
