# ESP + Raspberry Pi 温度モニタリングシステム

ESP-WROOM-02 (技適対応) や ESP32 系と DS18B20 温度センサーで構成された
温度センサーノードを、Raspberry Pi 上の Flask サーバー (自作 AP + トレンド
グラフ表示 + デバイス表示名管理) に定期送信し、可視化するシステム。

商業ビル管理業務の現場で、オーナー側 LAN に接続できない環境でも独立した
センサーネットワークを構築できるように設計。

<!-- tempserver-note -->
## 連載を追う人へ

ブログ連載「しまい込んでいた電子部品と、AI で形にできる温度監視システム」で作るのは
**[`tempserver/`](tempserver/)** です。1 ファイル 333 行の Flask サーバーで、導入手順は
[tempserver/README.md](tempserver/README.md) にまとまっています。

このリポジトリには温度サーバーの実装が複数入っています。用途が違うので、下の表で選んでください。

| ディレクトリ | 位置づけ |
|---|---|
| `tempserver/` | **連載版。まずこれ。** 1 ファイル完結。venv 不要 (apt で導入) |
| `temperature_server/` | 旧実装。`app/` パッケージ分割版 |
| `temperature_server_full/` | 旧実装。実運用版。テスト・CLI まで含む大きいもの |
| `temperature_server_deploy/` | 旧実装への PowerShell 配布スクリプト |

ESP 側のスケッチは連載版・旧実装で共通です。

## 設計方針: 3 層分離アーキテクチャ (2026-07-30 導入)

センサー ID・IP アドレス・表示名を **独立したレイヤーで管理**:

| レイヤー | 目的 | 実装 | 誰が決める |
|---|---|---|---|
| **識別** | このチップは物理的にどれか | MAC 由来 device_id (例: `ESP-A1B2C3`) | 自動 (チップ起動時) |
| **ネットワーク** | どの IP でつながるか | 方式D: MAC 由来の静的 IP を ESP が自己宣言 (`192.168.4.100 + (mac[5] & 0x7F)`) | 自動 (チップ起動時) |
| **表示** | 人間にとって何と呼ぶか | Flask の nickname テーブル (例: 冷却塔1) | ダッシュボード管理者 |

**結果**:
- ESP スケッチは **全チップ共通、書換え不要でコピペ書込み可能**
- 重複しない (MAC は物理的にユニーク)
- チップ交換時は dnsmasq の 1 行差替えで IP・表示名を継承
- 詳細: [outputs/docs/デバイス識別設計.md](docs/デバイス識別設計.md)

## システム構成

**パターン A (主流): 各センサーが直接 Pi の AP へ WiFi POST**

```
[ESP-WROOM-02 or ESP32] × N 台
       │  WiFi (DHCP、dnsmasq 予約で固定 IP)、HTTP POST /api/temperature
       ▼
[Raspberry Pi (wlan1 = AP 192.168.4.1)]
       │  SQLite + Flask + Chart.js + nickname 管理
       ▼
[wlan0 = ビル無料 WiFi 経由]
       ▼
[Windows ブラウザ / (将来) Tailscale で外部アクセス]
```

**パターン B: ESP-NOW でセンサー → ESP32 Master → Pi**

```
[ESP32/ESP32-C3 センサー] × N 台
       │  ESP-NOW (WiFi 認証不要、低レイテンシ、DeepSleep 特化)
       ▼
[ESP32 Master] ─── USB Serial ──→ [Raspberry Pi + Flask]
```

## ディレクトリ構成

### ESP スケッチ (全て MAC ベース device_id、コピペ書込み対応)

| フォルダ | チップ | 通信方式 | 用途 |
|---|---|---|---|
| `ESP8266_DeepSleep_FixedIP_Sensor/` | ESP-WROOM-02 | WiFi 直接 POST | **本番用** |
| `ESP8266_DeepSleep_FixedIP_Sensor_debug/` | ESP-WROOM-02 | WiFi 直接 POST | **開発時デバッグ用** (Serial 出力有効、MAC 表示) |
| `ESP8266_DeepSleep_FixedIP_Sensor_LED/` | ESP-WROOM-02 | WiFi 直接 POST | **★現地トラブルシューティング用 (恒久保持)** LED 3 色で状態表示 |
| `ESP32_DS18B20_WiFi/` | ESP32 | WiFi 直接 POST | 常時給電向け、ノンスリープ |
| `ESP32_DS18B20_WiFi_Battery/` | ESP32 | WiFi 直接 POST + DeepSleep | 電池運用、電圧監視付き |
| `ESP32_ESPNOW_Master/` | ESP32 | ESP-NOW 受信 + Serial 出力 | ESP-NOW ハブ (受信専用) |
| `ESP32_ESPNOW_Sensor/` | ESP32 | ESP-NOW 送信 | ESP-NOW センサー (ノンスリープ) |
| `ESP32C3_ESPNOW_Battery_Sensor/` | ESP32-C3 | ESP-NOW 送信 + DeepSleep | 電池運用の ESP-NOW センサー |
| `ESP_MAC_Address_Getter/` | ESP32/ESP8266 | (書込み用ユーティリティ) | MAC 確認用。**方式D では必須ではない** (ESP-NOW ピア指定時に使う) |

**フォルダ名の "FixedIP" について**: 名前のとおり ESP 側で固定 IP を宣言する
方式 (方式D) です。ただし固定値を手で書くのではなく、MAC から自動算出します
(`192.168.4.(100 + mac[5] & 0x7F)`)。スケッチは全チップ同一のままで済みます。

### 配線ガイド

| フォルダ | 内容 |
|---|---|
| `ESP8266_BareModule_Wiring/` | ブレッドボード配線ガイド、電池駆動配線ガイド |
| `RaspberryPi_AP_Setup/` | AP 構築ガイド、USB WiFi ドライバ導入ガイド |

### Pi 側 Flask サーバー

| フォルダ | 内容 |
|---|---|
| `temperature_server_full/` | ★**Flask 本体 (canonical、公開ソース)** — `install.sh` 一発で venv + systemd 導入 |
| `i2c_lcd_display/` | 現地ステータス表示 (I2C 20x4 LCD、`install_service.sh` で venv + systemd 導入) |
| `temperature_server_deploy/` | 過去のデプロイスクリプト・DHCP 予約ガイド (**非採用**、参考資料) |

### 統合ドキュメント (公開向け入口)

| ファイル | 内容 |
|---|---|
| `README.md` | 本ファイル (システム全体概要 + インストール手順) |
| `docs/初心者向け_WiFi設定ガイド.md` | ★★**初めての人はまず読む** — WiFi 認証情報の書換え手順 (9 か所) |
| `docs/デバイス識別設計.md` | ★3 層分離アーキテクチャの設計思想 |
| `docs/Arduino_IDE_設定ガイド.md` | 生 ESP-WROOM-02 の書込み設定・手順 |
| `docs/RaspberryPi_セットアップガイド.md` | Pi 全体の構築手順 (OS 導入 → 運用まで) |
| `docs/ESPNOW_統合ガイド.md` | ESP-NOW 選択時のセットアップ手順 |
| `docs/ESPNOW_MAC_ADDRESS_GUIDE.md` | ESP-NOW ピア用 MAC アドレス取得詳細 |
| `docs/I2C_LCD_接続と設置ガイド.md` | HD44780 20x4 LCD 導入手順 |
| `docs/USB_Camera_セットアップガイド.md` | USB Web カメラ (UVC) 導入・トラブルシューティング |
| `docs/Tailscale_導入ガイド.md` | 遠隔 SSH / ダッシュボードアクセス (VPN オーバーレイ) |
| `temperature_server_deploy/dnsmasq_mac_reservation.md` | DHCP 予約設定 (**非採用**。方式D に移行済み、参考資料として保存) |
| `temperature_server_full/docs/esp_devices/` | ESP-NOW 詳細実装ガイド |
| `ARCHIVE.md` | レガシー資産・削除候補の一覧 (詳細はそちら参照) |

### 現地表示器 (Pi 併設のオプション機器)

| フォルダ | 内容 |
|---|---|
| `i2c_lcd_display/` | ★**HD44780 20x4 I2C LCD** (稼働中)。日付/時刻/AP/WLAN/CAM/センサー行 × 2、RSSI ↔ 経過時間の交互表示による通信途絶検知 |
| `nokia5110_display/` | (廃止) Nokia 5110 SPI 版。ハードウェア故障で I2C LCD に切替済み。ARCHIVE.md 参照 |

### レガシー / 削除候補

詳細は `ARCHIVE.md` に集約。主なもの:
- `ESP8266_DS18B20_HTTPPOST/`, `ESP8266_DS18B20_Serial/`, `ESP8266_ESPNOW_Sensor/` — 初期試作、本番不採用
- `temperature_server/` — 中間版 Flask (temperature_server_full が canonical)
- `nokia5110_display/` — ハード故障で廃止
- 各種 `_synctest*.txt`, 旧 audit md 群 — 履歴目的のみ

---

## 🔰 GitHub から clone した人がまず読むもの

このリポジトリは公開のため、**WiFi の SSID/パスワードはプレースホルダ (`YOUR_AP_SSID_HERE` / `YOUR_AP_PASSWORD_HERE`)** に置換されています。動かす前に必ず:

→ **`docs/初心者向け_WiFi設定ガイド.md`** を読んで、9 か所 (Pi 側 2 + ESP スケッチ 7) の書換えを実施してください。所要時間 15 分。

.env ファイルも初回は `.env.example` からコピーが必要です:
```bash
cd temperature_server_full
cp .env.example .env
# .env を開いて AP_SSID / AP_PASSWORD / SECRET_KEY を書換え
```

## インストール順序 (公開版、venv 前提)

> **注意:** この節は旧実装 (`temperature_server/` `temperature_server_full/`) の手順で、venv を前提にしています。
> 連載版 `tempserver/` は venv を使いません (`sudo apt install -y python3-flask python3-serial sqlite3`)。
> 導入手順は [tempserver/README.md](tempserver/README.md) を参照してください。


新規に Pi を組んで一から立ち上げる場合、以下の順で実行:

```
[1] Raspberry Pi OS Trixie 導入 + I2C/カメラ有効化 (raspi-config)
    → docs/RaspberryPi_セットアップガイド.md

[2] wlan1 = USB WiFi ドングルで AP 化 (hostapd + dnsmasq)
    → RaspberryPi_AP_Setup/Raspberry Pi DHCPAPセットアップガイド.md
    → RaspberryPi_AP_Setup/ArcherT2UPlus_ドライバー導入.md (Archer T2U Plus 使用時)

[3] Flask 本体を導入 (venv 自動生成、systemd 登録まで一発)
    cd /home/pi
    git clone <repo> temperature_server        # or scp で転送
    cd temperature_server
    bash install.sh                            # ← 全部非対話

[4] (任意) 現地 LCD 表示器を導入
    cd /home/pi/i2c_lcd_display
    bash install_service.sh                    # ← I2C アドレス自動検出

[5] (任意) USB カメラを繋げてストリーミング機能を使う
    → docs/USB_Camera_セットアップガイド.md

[6] (任意) Tailscale で外部から SSH / ダッシュボードにアクセス
    → docs/Tailscale_導入ガイド.md
```

**再デプロイ / アップデート時**:

```bash
cd /home/pi/temperature_server
git pull                                       # or 手動で scp
bash install.sh                                # 冪等 (venv 再作成しない)
```

## 新チップ追加ワークフロー (5 分で完了)

```
Step 1: 本番スケッチを新チップに書込み (書換え無しでコピペ)
  ESP8266_DeepSleep_FixedIP_Sensor.ino をそのまま書込む
  ※ Pi 側の作業は不要。MAC から device_id と IP が自動で決まる

Step 2: ダッシュボードで動作確認 + nickname 割当
  http://<Pi の LAN IP>:5000/management → 表示名管理タブ
  → "ESP-A1B2C3" が現れたら「冷却塔1」等の表示名を保存

Step 3: IP の重複確認
  device 一覧で ip_address が既存機と重ならないことを確認
  (MAC 末尾 7 bit が一致すると衝突しうる。詳細は docs/デバイス識別設計.md)
```

詳細手順: `temperature_server_deploy/dnsmasq_mac_reservation.md`

## スケッチ選択ガイド

### ESP-WROOM-02 (技適重視、日本国内) を使う場合

1. **通常の運用**: `ESP8266_DeepSleep_FixedIP_Sensor/` (本番用)
2. **新しい基盤を作った時 or 現地展開時**: `ESP8266_DeepSleep_FixedIP_Sensor_LED/`
   - **恒久保持推奨**。現地で PC を持ち込めない状況で LED 3 色から一次切り分け
   - 動作確認後もそのまま常用 or 本番版に載せ替え
3. **開発時にシリアルログを見たい**: `ESP8266_DeepSleep_FixedIP_Sensor_debug/`

### ESP32 系を使う場合

1. **常時給電 (AC アダプタ) の設置**: `ESP32_DS18B20_WiFi/`
2. **電池駆動で WiFi 直接送信**: `ESP32_DS18B20_WiFi_Battery/`
3. **ESP-NOW で低電力**: `ESP32C3_ESPNOW_Battery_Sensor/` + `ESP32_ESPNOW_Master/`

### 判断フローチャート

```
チップ選択:
  技適重視/低価格         → ESP-WROOM-02
  処理性能/BLE           → ESP32
  極小/USB シリアル内蔵    → ESP32-C3

通信方式選択:
  シンプルさ最優先        → WiFi 直接 POST
  電池寿命最優先          → ESP-NOW
  現地 PC 接続不可・切り分け要 → LED 診断版 (WiFi)
```

## API 仕様 (ESP → Flask)

### WiFi 直接 POST (ESP8266 / ESP32 WiFi 版)

```
POST http://192.168.4.1:5000/api/temperature
Content-Type: application/json

{
  "device_id":     "ESP-A1B2C3",         ← MAC 下位 3 バイトから自動生成
  "name":          "ESP-A1B2C3",         ← nickname 未設定時のフォールバック
  "temperature":   24.50,
  "temp":          24.50,
  "ip_address":    "192.168.4.208",      ← dnsmasq 予約で決まる
  "voltage":       3.31,
  "battery_percent": 78,
  "battery_mode":  1,
  "rssi":          -65,
  "signal_strength": -65
}
```

Flask 側で受信 → SQLite 挿入 → ダッシュボードで nickname 優先表示。

### nickname 管理 API

```
GET    /api/nicknames                 - 全 nickname 一覧
PUT    /api/nicknames/<device_id>     - 表示名を設定 (body: {"nickname": "冷却塔1"})
DELETE /api/nicknames/<device_id>     - 表示名を削除
```

管理画面 (`/management` → 「表示名管理」タブ) から GUI で操作可能。

### 重複検知 (WARN ログ)

同じ `device_id` で違う `ip_address` からの POST を検知 → Flask ログに `[DUPLICATE device_id WARNING]` 出力。MAC ベースなら通常発生しないが、事故検知の保険。

## 現行状態 (2026-09-03 時点)

- 3 層分離アーキテクチャ (MAC ベース device_id + MAC 由来静的 IP + nickname) 導入
- ESP スケッチ全種 MAC ベース化完了 (ESP-WROOM-02 / ESP32 WROOM-DA / XIAO ESP32-C3、WiFi 直接 POST + ESP-NOW 両パターン)
- ネットワーク層は方式D (ESP 側で MAC 由来の静的 IP を宣言) を canonical とする。DHCP 予約ガイドは参考資料に降格
- Flask 側の重複検知 + rssi/signal_strength 両受理 実装済
- ESP-NOW パイプライン (子機 → Master → Serial → Flask) end-to-end 動作確認済、Master 側で物理層 RSSI 取得実装済
- **HD44780 20x4 I2C LCD による現地ステータス表示** (半角カナ nickname / CGRAM RSSI バー / カメラ・AP・WLAN アイコン / RSSI ↔ 経過時間の交互表示)
- **USB Web カメラ MJPEG ストリーミング復活** (opencv-python-headless>=4.10.0.84、NumPy 2 対応)
- **Tailscale による遠隔アクセス** (Google 認証 + MagicDNS + 鍵認証)
- 全コンポーネントに `install.sh` / `install_service.sh` を整備 (venv 自動生成、systemd 登録、非対話)

## ライセンス

MIT (予定)

## 更新履歴

- 2026-07-14 Pi (Trixie) + Archer T2U Plus (RTL8821AU) で AP 構築完了
- 2026-07-15 Flask サーバー初版
- 2026-07-16 ESP 実機の HTTP POST 疎通確認
- 2026-07-17 コード監査と方針 P (既存 Flask 実装ベース) 完了、nickname 機能実装
- 2026-07-18 ESP-WROOM-02 本番版のスケッチ修正、LED 診断版作成
- 2026-07-28 ESP32/ESP-NOW スケッチ群を Z: に統合、重複検知機能追加
- 2026-07-30 **3 層分離アーキテクチャ (MAC ベース device_id + DHCP 予約) に全面移行**
- 2026-09-03 **ネットワーク層を方式D (MAC 由来の静的 IP を ESP 側で自己宣言、`.100-.227`) に変更**。DHCP プールは `.228-.254` の一時接続用のみ。DeepSleep 時の DHCP 折衝を削減 + 新チップ追加時に Pi 側作業を不要化
- 2026-08-07 I2C 20x4 LCD 導入 (Nokia 5110 は故障で退役)、半角カナ + CGRAM アイコン
- 2026-08-09 LCD 交互表示 (RSSI ↔ 経過時間) で通信途絶を可視化
- 2026-08-11 Tailscale 遠隔アクセス導入
- 2026-08-12 USB カメラ MJPEG ストリーミング復活 (opencv NumPy 2 対応版に更新)、公開向け整理: `install.sh` 各所整備、`ARCHIVE.md` 追加

## 物理接続の再確認 (2026-07-30 追記)

- **Master ESP32 は Pi に常時 USB 接続** (システム構成パターン B の運用)
- Windows PC への USB 接続は Master スケッチ書込み時のみ
- Master の Serial 出力は Pi 側で `screen /dev/ttyUSB0 115200` または
  `serial_reader.py` が拾って Flask へ転送
- 子機 (ESP-NOW センサー) は Pi に USB 接続しない (WiFi/ESP-NOW 経由で通信)
