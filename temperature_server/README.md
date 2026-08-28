# ESP8266 温度モニターサーバー (Raspberry Pi + Flask)

ESP8266 (ESP-WROOM-02) + DS18B20 の温度センサーノードからの HTTP POST を受信し、SQLite に保存、Chart.js でトレンドグラフを表示する Flask アプリケーション。

## 特徴 / 参照リポジトリからの改善点

`opticalbreeze/dual-wifi-temperature-monitoring` を参照に構築しつつ、以下 5 点を改善:

| 参照の問題 | 本実装の対処 |
|---|---|
| `get_all_latest()` のネスト ロック取得によるデッドロック | 単一 SQL クエリで全センサー最新値を取得 (INNER JOIN + MAX(id)) |
| タイムスタンプ形式ミスマッチ (ISO 形式 vs 素朴形式) | 挿入・クエリ両方で `strftime('%Y-%m-%d %H:%M:%S')` に統一。`TS_FORMAT` 定数で共有 |
| ESP からのタイムスタンプ受信前提の設計 | ESP はタイムスタンプ送らず、サーバー側で JST 受信時刻を付与 |
| ダミーデータが本番 DB に混入 | 環境変数 `DB_PATH` でテスト用 DB と本番 DB を分離 |
| カメラ系など未使用機能の混在 | 温度ロガー機能に集中、他機能は排除 |

## ディレクトリ構成

```
temperature_server/
├── run.py                       # エントリーポイント
├── app/
│   ├── __init__.py              # Flask アプリファクトリ
│   ├── database.py              # SQLite ラッパ
│   ├── auth.py                  # Basic 認証デコレータ
│   └── routes.py                # HTTP エンドポイント
├── templates/
│   ├── base.html                # 共通レイアウト
│   ├── index.html               # ダッシュボード
│   └── sensor.html              # 詳細ページ (Chart.js)
├── data/                        # SQLite DB (gitignore)
├── logs/                        # ログ (gitignore)
├── requirements.txt
├── temperature-server.service   # systemd unit
├── .env.template                # 環境変数テンプレート
└── README.md
```

## セットアップ手順 (Raspberry Pi)

### 1. プロジェクトを配置

```bash
# git 管理する場合
cd ~
git clone <your-repo> temperature_server
# または ZIP をコピー
```

### 2. Python 仮想環境と依存インストール

```bash
cd ~/temperature_server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 環境変数を設定

```bash
cp .env.template .env
nano .env
# BASIC_AUTH_PASSWORD を安全な値に変更
```

### 4. 単体起動テスト (systemd 導入前の確認)

```bash
cd ~/temperature_server
source venv/bin/activate
python run.py
```

別のターミナルから疎通確認:

```bash
# ヘルスチェック
curl http://localhost:5000/health

# ダミー POST (静的IP版スケッチ ESP8266_DeepSleep_FixedIP_Sensor.ino からの JSON を模擬)
curl -X POST http://localhost:5000/api/temperature \
    -H "Content-Type: application/json" \
    -d '{
      "device_id": "ESP8266_ip208_30sec",
      "name": "DS18B20-ESP8266-208",
      "temperature": 24.50,
      "temp": 24.50,
      "ip_address": "192.168.4.208",
      "voltage": 3.31,
      "battery_percent": 78,
      "battery_mode": 1,
      "signal_strength": -65
    }'

# ダミー POST (STEP 2 版 DHCP スケッチのレガシー互換)
curl -X POST http://localhost:5000/api/sensor \
    -H "Content-Type: application/json" \
    -d '{
      "device_id": "test-01",
      "voltage": 3.31,
      "battery_percent": 78.5,
      "is_battery_mode": true,
      "rssi_dbm": -65,
      "sensors": [
        {"index": 0, "address": "28FFA1B2C3D4E5F6", "temp_c": 24.50}
      ]
    }'
```

ブラウザで `http://<Raspberry Pi の IP>:5000/` を開いて Basic 認証を突破するとダッシュボードが表示されます。

### 5. systemd サービス化 (常時起動)

```bash
sudo cp temperature-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable temperature-server.service
sudo systemctl start temperature-server.service
sudo systemctl status temperature-server.service --no-pager
```

ログ確認:

```bash
sudo journalctl -u temperature-server -f
```

## API 仕様

### POST /api/temperature (認証なし) — 方針 A 主流

ESP8266 静的 IP 版スケッチ (`ESP8266_DeepSleep_FixedIP_Sensor.ino`) が投稿する。認証は無し (LAN 内前提)。

**リクエスト body** (フラット構造、1 リクエスト = 1 センサー):

```json
{
  "device_id": "ESP8266_ip208_30sec",
  "name": "DS18B20-ESP8266-208",
  "temperature": 24.50,
  "temp": 24.50,
  "ip_address": "192.168.4.208",
  "voltage": 3.31,
  "battery_percent": 78,
  "battery_mode": 1,
  "signal_strength": -65
}
```

- `device_id` と `temperature` (または `temp`) が必須。それ以外は任意
- `temperature` 優先、なければ `temp` を採用 (既存スケッチ互換のため両方受け付ける)
- `battery_mode` は int (0/1) または bool のどちらでも可
- サーバー内部では `sensor_index=0`、`sensor_addr=NULL` として保存 (1 チップ 1 センサー前提)
- `name` / `ip_address` は新設列に格納 (ダッシュボードで表示)
- サーバー側で受信時刻 (JST 素朴形式) を付与

**レスポンス**:

```json
{"status": "ok", "saved": 1, "received_at": "2026-07-15 14:30:15"}
```

### POST /api/sensor (認証なし) — レガシー (STEP 2 DHCP 版互換)

STEP 2 の DHCP 版スケッチ (`ESP8266_DS18B20_HTTPPOST.ino`) が投稿する。方針 A では主流ではないが互換維持。

**リクエスト body** (ネスト構造、1 リクエストで複数センサー可):

```json
{
  "device_id": "esp8266-01",
  "voltage": 3.31,
  "battery_percent": 78.5,
  "is_battery_mode": false,
  "rssi_dbm": -65,
  "sensors": [
    {"index": 0, "address": "28FFA1B2C3D4E5F6", "temp_c": 24.50},
    {"index": 1, "address": "28AA0123456789AB", "temp_c": null}
  ]
}
```

- `sensors[]` 配列は 1 リクエストで複数レコードに展開して DB 挿入
- `temp_c: null` は「欠測」として NULL 保存

**レスポンス**:

```json
{"status": "ok", "saved": 2, "received_at": "2026-07-15 14:30:15"}
```

### GET /api/sensors (認証あり)

全デバイス各センサーの最新値。

### GET /api/sensor/<device_id>/readings?hours=24 (認証あり)

時間範囲データ + 統計。

**クエリパラメータ**:
- `hours`: 数値 (デフォルト 24)

**レスポンス**:

```json
{
  "device_id": "esp8266-01",
  "hours": 24,
  "count": 1440,
  "readings": [...],
  "stats": [
    {"sensor_index": 0, "sensor_addr": "...", "count": 720, "min_temp": 18.5, "max_temp": 25.3, "avg_temp": 22.1}
  ]
}
```

### GET /api/export/<device_id>?hours=24 (認証あり)

CSV ダウンロード。

### GET /health (認証なし)

ヘルスチェック。監視ツール向け。

## DB スキーマ

```sql
CREATE TABLE readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id    TEXT NOT NULL,
    sensor_index INTEGER,          -- /api/temperature 経由は常に 0
    sensor_addr  TEXT,             -- /api/temperature 経由は NULL
    temp_c       REAL,
    voltage      REAL,
    battery_pct  REAL,
    is_battery   INTEGER,
    rssi_dbm     INTEGER,
    received_at  TEXT NOT NULL,    -- JST 素朴形式 '%Y-%m-%d %H:%M:%S'
    name         TEXT,             -- /api/temperature の "name" 表示名
    ip_address   TEXT              -- /api/temperature の "ip_address" 固定IP
);
CREATE INDEX idx_device_time ON readings(device_id, received_at);
CREATE INDEX idx_time ON readings(received_at);
```

既存 DB からのマイグレーションは `init_db()` 内で `ALTER TABLE ADD COLUMN` を try/except で自動処理する (再起動時に列が無ければ追加、あれば OperationalError を無視)。

## 運用メモ

- **DB サイズ**: 1 デバイス 2 センサー、1 分間隔で 24 時間動くと 2880 レコード/日。1 年で約 100 万レコード = 数十 MB 程度。SD カード運用でも問題なし
- **古データの削除**: 本ガイドは無制限保存を想定 (ユーザー選定)。削除が必要なら `sqlite3 data/temperature.db "DELETE FROM readings WHERE received_at < '2026-01-01'"`
- **バックアップ**: `data/temperature.db` を定期コピー (ホット バックアップも可、SQLite が並行アクセスを扱う)
- **タイムゾーン**: システム時刻を `Asia/Tokyo` (JST) に設定していることが前提。`sudo timedatectl set-timezone Asia/Tokyo` で確認/設定
- **ポート変更**: `.env` の `PORT` を変えて systemd restart

## トラブルシューティング

| 症状 | 原因/対処 |
|---|---|
| `/api/sensor` POST が 400 | JSON パース失敗。`Content-Type: application/json` ヘッダ、body の中身をログ (`journalctl -u temperature-server -f`) で確認 |
| ダッシュボードで 401 | `.env` の `BASIC_AUTH_USER` / `PASSWORD` を確認 |
| グラフが空 | `hours` パラメータ内にデータがない、または受信時刻の書式ズレ (通常発生しないが念のため `sqlite3 data/temperature.db "SELECT * FROM readings LIMIT 5"` で received_at 形式を確認) |
| systemd で起動失敗 | `sudo journalctl -u temperature-server -n 50` でエラー確認。venv パス、DB_PATH の書き込み権限を疑う |

## ライセンス

MIT (自由に改変・利用可)
