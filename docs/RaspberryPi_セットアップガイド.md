# Raspberry Pi 統合セットアップガイド

温度モニタリングシステムの Pi 側 (AP + Flask サーバー) を新規 SD カードから
運用状態まで一気通貫で構築する手順書。

## 前提条件

| 項目 | 値 |
|---|---|
| ハードウェア | Raspberry Pi 4B (4GB or 8GB) / Pi 5 (4GB 以上) も可 |
| OS | Raspberry Pi OS **Trixie (Debian 13) 64-bit** |
| OS バリアント | Desktop 版 (初心者・GUI 復旧向き) / Lite 版 (経験者・SSH 前提) どちらでも動作 |
| カーネル | 6.12.75+rpt-rpi-v8 (2026-07 時点) |
| USB WiFi (AP 用) | TP-Link Archer T2U Plus (RTL8821AU チップ) |
| SD カード | 32GB 以上、Class 10 (A2 推奨) |
| ユーザー | `pi` (デフォルト) |
| ホスト名 | 任意 (例: `takemetothehospital`) |

**OS バリアント選択の目安**:
- 初回セットアップに詰まったときにモニタ+キーボードで直したい、非開発者向け
  → **Desktop 版** (`Raspberry Pi OS (64-bit)`)。詳細は `blog/第3回_...` 参照
- 本ガイドと同等の経験値がある、SSH のみで完結したい → **Lite 版** (`Raspberry Pi OS Lite`)

本ガイドの手順はどちらのバリアントでも動作します (differ は初回起動時に
デスクトップ画面が出るか出ないかだけ)。

**ネットワーク構成**:
- `wlan0` (オンボード Broadcom) → ビル管理業務先の無料 WiFi (キャプティブポータル型)
- `wlan1` (USB Archer T2U Plus / RTL8821AU) → センサー用 AP (192.168.4.1/24)

---

## 全体像 (完成形の系統図)

```
[ESP-WROOM-02 ×N] → wlan1 AP (192.168.4.1)
                        │
                    Raspberry Pi (systemd)
                        │
                    Flask (0.0.0.0:5000)
                        │
                    wlan0 (ビル無料 WiFi 経由でアクセス)
                        │
                    Windows ブラウザ (dashboard/management)
```

---

## 手順一覧 (章)

1. OS 導入と SSH 有効化
2. WiFi ドライバ (RTL8821AU) 導入
3. wlan1 の AP 構築 (hostapd + dnsmasq + NetworkManager 除外)
4. wlan0 の設定 (ビル WiFi 接続)
5. Flask サーバー展開
6. systemd サービス化
7. 動作確認とトラブルシューティング

---

## 1. OS 導入と初期設定

### 1.1 Imager で SD を焼く

Raspberry Pi Imager から:
- OS: **Raspberry Pi OS (64-bit) - Trixie**
- ストレージ: 対象 SD カード
- 詳細設定 (歯車アイコン):
  - ホスト名: 任意 (例: `takemetothehospital`)
  - ユーザー名 / パスワード: `pi` / 任意
  - **SSH 有効化 (パスワード認証)** をチェック
  - WiFi は wlan0 側の初期接続用に自宅 or 一時 SSID を設定してよい
  - タイムゾーン: `Asia/Tokyo`
  - キーボードレイアウト: JP

書き込み完了後 SD を Pi に挿して起動。

### 1.2 初回 SSH

Windows PowerShell から (`<hostname>` は §1.1 で指定した名前に置換):
```powershell
ssh pi@<hostname>.local
# 例: ssh pi@takemetothehospital.local
# または IP 指定
ssh pi@192.168.11.XXX
```

**Desktop 版を選んだ場合**: 初回は HDMI モニタ + USB キーボードで直接
デスクトップに入り、右上 WiFi アイコン確認と `hostname -I` で IP 確認 →
Windows から SSH、の順が復旧しやすい。詳細は `blog/第3回_RaspberryPiに
OSを入れてSSHで入る.md` の §4-5 を参照。

### 1.3 システム更新

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

再起動後に SSH 再接続。

### 1.4 タイムゾーン確認

```bash
timedatectl
# → Time zone: Asia/Tokyo が表示されれば OK
```

---

## 2. USB WiFi ドライバ (RTL8821AU) 導入

TP-Link Archer T2U Plus (VID:2357 PID:0120) は **RTL8821AU** チップ。Trixie
純正カーネルには対応ドライバが入っていない。DKMS で追加インストールする。

### 2.1 正しいドライバソース

⚠️ **重要**: 「T2U Plus は 8821au ではなく 8812au」と誤情報が Web に多い。正解は
以下の通り:

- ✅ **`morrownr/8821au-20210708`** (v5.12.5.2、動作確認済) を使う
- ❌ `morrownr/8812au-20210820` は EPERM で hostapd が起動しない (3 日ハマる罠)

### 2.2 依存インストール

```bash
sudo apt install -y build-essential dkms git raspberrypi-kernel-headers linux-headers-generic
```

### 2.3 ソース取得と DKMS 登録

```bash
cd ~
git clone https://github.com/morrownr/8821au-20210708.git
cd 8821au-20210708

# DKMS でビルド + カーネルモジュール登録
sudo ./install-driver.sh
```

対話プロンプトで:
- Editor 設定: `n` (デフォルト値のまま)
- 再起動: `y`

### 2.4 動作確認

再起動後:
```bash
lsmod | grep 8821au   # モジュールがロードされているか
ip link show wlan1     # wlan1 が認識されているか
iwconfig wlan1         # 無線モードが確認できるか
```

`wlan1` が上記コマンドで見えれば成功。

### 2.5 詳細と切り分け

- `outputs/RaspberryPi_AP_Setup/ArcherT2UPlus_ドライバー導入.md` に詳細手順
- 過去に間違ったドライバを入れた場合は
  `outputs/RaspberryPi_AP_Setup/cleanup-driver-environment.sh` でクリーンアップ

---

## 3. wlan1 の AP 構築 (hostapd + dnsmasq)

### 3.1 パッケージ導入

```bash
sudo apt install -y hostapd dnsmasq
sudo systemctl unmask hostapd
```

### 3.2 NetworkManager から wlan1 を除外

NetworkManager が wlan1 を触ると hostapd と競合する。以下で除外:

```bash
sudo tee /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf > /dev/null << 'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan1
EOF

sudo systemctl restart NetworkManager
```

### 3.3 wlan1 に静的 IP を割り当て (systemd unit で管理)

```bash
sudo tee /etc/systemd/system/wlan1-static-ip.service > /dev/null << 'EOF'
[Unit]
Description=Assign static IP to wlan1 for AP
After=NetworkManager.service
Before=hostapd.service dnsmasq.service

[Service]
Type=oneshot
ExecStart=/usr/sbin/ip addr flush dev wlan1
ExecStart=/usr/sbin/ip addr add 192.168.4.1/24 dev wlan1
ExecStart=/usr/sbin/ip link set wlan1 up
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wlan1-static-ip.service
sudo systemctl start wlan1-static-ip.service
```

### 3.4 hostapd 設定

```bash
sudo tee /etc/hostapd/hostapd.conf > /dev/null << 'EOF'
interface=wlan1
driver=nl80211
ssid=YOUR_AP_SSID_HERE
hw_mode=g
channel=6
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=YOUR_AP_PASSWORD_HERE
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

# hostapd デフォルト設定ファイルへのパス指定
sudo sed -i 's|^#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl start hostapd
sudo systemctl status hostapd --no-pager
```

`Active: active (running)` が出れば OK。

### 3.5 dnsmasq 設定 (DHCP プール + MAC 予約 = 本命)

**重要**: 本プロジェクトは **3 層分離アーキテクチャ** (2026-07-30 導入) で運用します。
IP 割当は Pi 側 dnsmasq の DHCP 予約で管理し、ESP スケッチは MAC から自動生成される
device_id を使うため、per-chip の書換えは不要です。詳細は
`outputs/docs/デバイス識別設計.md` 参照。

基本設定 (プール範囲と予約領域を分ける):

```bash
sudo tee /etc/dnsmasq.d/wlan1.conf > /dev/null << 'EOF'
interface=wlan1
bind-interfaces
domain-needed
bogus-priv
no-resolv
listen-address=192.168.4.1

# DHCP プール範囲 (未予約の動的割当領域、一時接続用)
dhcp-range=192.168.4.100,192.168.4.199,255.255.255.0,24h

# ===== ESP デバイスの MAC-IP 予約 (200-254 は予約専用領域) =====
# 新チップ追加時はここに以下の書式で 1 行追加:
#   dhcp-host=<MAC 小文字コロン区切り>,<予約 IP>,<hostname>
# 例:
# dhcp-host=84:cc:a8:a1:b2:c3,192.168.4.208,ESP-A1B2C3
# dhcp-host=84:cc:a8:d4:e5:f6,192.168.4.209,ESP-D4E5F6
EOF

sudo systemctl enable dnsmasq
sudo systemctl start dnsmasq
sudo systemctl status dnsmasq --no-pager
```

**新チップ追加時の手順** (詳細):
`outputs/temperature_server_deploy/dnsmasq_mac_reservation.md` に **canonical
運用手順** を記載。要点:

1. `ESP_MAC_Address_Getter.ino` で新チップの MAC を取得
2. `/etc/dnsmasq.d/wlan1.conf` に `dhcp-host=<MAC>,<IP>,<hostname>` を 1 行追加
3. `sudo systemctl restart dnsmasq`
4. 本番スケッチを新チップに **書換え無しでコピペ書込み**
5. ダッシュボード管理画面で nickname 割当

---

## 4. wlan0 の設定 (ビル無料 WiFi 接続)

### 4.1 通常運用 (自宅・自席の WiFi)

Raspberry Pi Imager で最初に設定した SSID/pass で自動接続される。追加変更は
NetworkManager で:

```bash
nmcli device wifi list ifname wlan0
nmcli device wifi connect "SSID_NAME" password "PASSWORD" ifname wlan0
```

### 4.2 ビル無料 WiFi (キャプティブポータル型) 接続

商業ビルの無料 WiFi はブラウザで「同意する」ボタンを押さないと外に出れない。
自動化は Selenium で対応可能だが、本ガイドの範囲外。

現地運用では以下の手順:
1. 現地に Pi を持ち込む前に、テスト SSID で通常接続を確認
2. 現地でオープン SSID に接続 (nmcli or 自動)
3. 一度 Pi のブラウザ (or curl でリダイレクト先取得) からキャプティブ認証を通す

Selenium 自動化コードは元プロジェクト
`opticalbreeze/dual-wifi-temperature-monitoring` の `free_wifi/` を参考にする
予定。詳細は今後の作業で追加。

### 4.3 wlan0 に静的 IP (推奨)

nmcli で:
```bash
# 接続名を確認
nmcli connection show

# 例: 接続名が "preconfigured" の場合
sudo nmcli connection modify preconfigured ipv4.addresses 192.168.11.200/24
sudo nmcli connection modify preconfigured ipv4.gateway 192.168.11.1
sudo nmcli connection modify preconfigured ipv4.dns 8.8.8.8,1.1.1.1
sudo nmcli connection modify preconfigured ipv4.method manual
sudo nmcli connection up preconfigured
```

---

## 5. Flask サーバー展開

### 5.1 初回展開

`outputs/temperature_server_deploy/README.md` の Phase 1〜4 に従う。要点:

**PowerShell から Pi へ scp:**
```powershell
cd Z:\afterNK\ESPSARVER\outputs
scp -r temperature_server_full pi@192.168.11.200:/home/pi/
```

**Pi 側でリネームと venv 構築:**
```bash
ssh pi@192.168.11.200

mv ~/temperature_server_full ~/temperature_server
cd ~/temperature_server

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# selenium で失敗したら
sed -i '/selenium/d' requirements.txt
pip install -r requirements.txt

mkdir -p data logs
```

### 5.2 .env の内容

`~/temperature_server/.env`:
```
FLASK_ENV=production
FLASK_DEBUG=False
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
SECRET_KEY=change-me-to-random-string-in-production

AP_INTERFACE=wlan1
STATION_INTERFACE=wlan0
AP_SSID=YOUR_AP_SSID_HERE
AP_PASSWORD=YOUR_AP_PASSWORD_HERE
AP_IP=192.168.4.1

SERIAL_ENABLED=False
ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000,http://192.168.4.1:5000,http://192.168.11.200:5000
```

---

## 6. systemd サービス化

### 6.1 unit ファイルを反映

```bash
sudo cp ~/temperature_server/systemd/temperature-server.service /etc/systemd/system/temperature-server.service
sudo systemctl daemon-reload
sudo systemctl enable temperature-server
sudo systemctl start temperature-server
sudo systemctl status temperature-server --no-pager -l
```

### 6.2 systemd unit の中身

```ini
[Unit]
Description=Temperature Server - Raspberry Pi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/temperature_server
Environment="PATH=/home/pi/temperature_server/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="VIRTUAL_ENV=/home/pi/temperature_server/venv"
ExecStart=/home/pi/temperature_server/venv/bin/python3 /home/pi/temperature_server/run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 6.3 ログの見方

```bash
# リアルタイム追跡
sudo journalctl -u temperature-server -f

# 直近 40 行
sudo journalctl -u temperature-server -n 40 --no-pager

# ファイル出力の追跡 (Python logging 側)
tail -f ~/temperature_server/logs/main.log
tail -f ~/temperature_server/logs/app.routes.api.log
```

---

## 7. 動作確認とトラブルシューティング

### 7.1 疎通テスト

```bash
# ヘルスチェック
curl http://localhost:5000/api/status

# ESP 模擬 POST
curl -X POST http://localhost:5000/api/temperature \
    -H "Content-Type: application/json" \
    -d '{"device_id":"test","temperature":25.0,"name":"test-sensor"}'
```

期待レスポンス (201 Created):
```json
{"status":"success","message":"Data received and stored","device_id":"test",...}
```

### 7.2 ブラウザ確認

Windows のブラウザで:
- `http://192.168.11.200:5000/` — ダッシュボード
- `http://192.168.11.200:5000/management` — 管理画面
- `http://192.168.11.200:5000/api/routes` — 全 API 一覧 (JSON)
- `http://192.168.11.200:5000/api/status` — システム情報 JSON

### 7.3 ESP → Flask 疎通確認

ESP を通電状態にした上で:
```bash
sudo journalctl -u temperature-server -f
```

30 秒周期で `[POST /api/temperature]` の 201 レスポンスが出れば疎通成功。

### 7.4 よくある問題

| 症状 | 原因 | 対処 |
|---|---|---|
| `systemctl start` で failed | Python 依存不足 | `sudo journalctl -u temperature-server -n 30` で `ModuleNotFoundError` を確認 → 該当 pkg を pip install |
| /api/temperature が 404 | routes.py の反映漏れ | `grep "/api/temperature" ~/temperature_server/app/routes/api.py` で確認、無ければ再 scp |
| /api/temperature が 500 with `unexpected keyword argument` | database.py の反映漏れ | 同上 |
| wlan1 が認識されない | ドライバ (8821au) 未導入 | §2 参照 |
| hostapd が起動しない (EPERM) | 8821au ではなく 8812au を入れてしまった | §2 参照、cleanup-driver-environment.sh で戻す |
| ESP から接続できない (DHCP 失敗) | dnsmasq 未起動 or dhcp-range 設定ミス | §3.5 参照、`sudo systemctl status dnsmasq` |
| wlan0 と wlan1 の名前が入れ替わる | udev の rename ルールが不安定 | 起動時に USB を必ず挿してから電源投入 |
| ブラウザ表示に変化がない | Chart.js は自動更新しない | `Ctrl+F5` 強制リロード |

### 7.5 ブラウザで表示が出ない時の切り分けフロー

Pi 側は正常なのにブラウザで `http://192.168.11.200:5000/` が表示されない、
という事象は「Pi 問題」「ネットワーク問題」「ブラウザ問題」の 3 階層に
分けて **上から順に確認** すると原因を素早く特定できる。

#### 第 1 階層: Pi (Flask) 側の健全性確認

Pi の SSH で以下 4 コマンドを順に実行:

```bash
# 1) Flask がどのアドレスで listen しているか
sudo ss -tlnp | grep :5000
# 期待: LISTEN 0.0.0.0:5000  (0.0.0.0 で LAN 全体を受ける)
# NG:  LISTEN 127.0.0.1:5000 (localhost のみ、LAN からは見えない)

# 2) Pi の wlan0 IP を確認
ip addr show wlan0 | grep 'inet '

# 3) Pi 自身から Pi の wlan0 IP へアクセスできるか
curl -sS http://$(ip -4 addr show wlan0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'):5000/api/status

# 4) ファイアウォールが 5000 を塞いでいないか
sudo ufw status 2>/dev/null
sudo nft list ruleset 2>/dev/null | grep -i 'reject\|drop'
```

すべて正常 (Flask が 0.0.0.0 で listen、curl で JSON 返却、firewall なし)
なら Pi 側は完全に健全。次は第 2 階層に進む。

**Flask が 127.0.0.1 でしか listen していない場合**:
```bash
grep FLASK_HOST /home/pi/temperature_server/.env
# FLASK_HOST=0.0.0.0 が無ければ以下で追記
echo 'FLASK_HOST=0.0.0.0' >> /home/pi/temperature_server/.env
sudo systemctl restart temperature-server
```

#### 第 2 階層: Windows 〜 Pi 間のネットワーク経路確認

Windows PowerShell で以下 3 コマンドを順に実行:

```powershell
# 1) Windows の IP アドレス (Pi と同一 LAN セグメントか)
ipconfig | Select-String "IPv4|adapter"
# 期待: 192.168.11.x (Pi の 192.168.11.200 と同じサブネット)
# NG:  192.168.1.x や 10.0.x.x なら Windows が別 WiFi

# 2) Pi の port 5000 に TCP 接続できるか
Test-NetConnection -ComputerName 192.168.11.200 -Port 5000
# 期待: TcpTestSucceeded : True

# 3) Windows 側から実際に HTTP を叩く
curl.exe http://192.168.11.200:5000/api/status
# 期待: JSON が返る (Pi の第 1 階層と同じ内容)
```

**curl.exe で JSON が返るなら**、Windows と Pi 間の通信は健全。
→ 問題はブラウザ側 (第 3 階層に進む)

**Windows IP が 192.168.11.x でない場合**、別 WiFi に接続されている。
Pi と同じ WiFi に接続し直す。

**Test-NetConnection が False で SSH (port 22) は通る場合**:
```powershell
Test-NetConnection -ComputerName 192.168.11.200 -Port 22
```
SSH は通って 5000 だけダメなら Windows Defender ファイアウォールの
アウトバウンドルールを確認。

#### 第 3 階層: ブラウザ固有の問題

curl.exe で JSON が返るのにブラウザだけ表示されない場合の対処 (上から順に試す):

**対処 1: タブを閉じて開き直す ★最も効果的**

経験上、これで解決するケースが最多。単なるリロードでは効かない場合が多い。

```
1. 対象のタブを × ボタンで閉じる
2. 新しいタブを開く (Ctrl + T)
3. アドレスバーに http://192.168.11.200:5000/ を入力
4. Enter
```

**対処 2: 強制リロード (キャッシュ無視)**

Ctrl + Shift + R または Ctrl + F5。単なる F5 (通常リロード) では効かない。

**対処 3: シークレット/プライベート ウィンドウで開く**

ブラウザ拡張機能や Cookie の影響を回避:
- Chrome / Edge: Ctrl + Shift + N
- Firefox: Ctrl + Shift + P

新ウィンドウで `http://192.168.11.200:5000/` を開く。

**対処 4: URL の scheme を確認**

アドレスバーが **HTTPS ではなく HTTP** になっているか:
- 正しい: `http://192.168.11.200:5000/`  (HTTP、S 無し)
- 誤り:  `https://192.168.11.200:5000/` (Flask は TLS 未対応で接続不可)

一度でも https:// でアクセスすると、ブラウザが HSTS 的な挙動で以降 https に
強制する場合がある。その時はブラウザ設定でホスト設定をリセットするか、
別ブラウザで確認。

**対処 5: キャッシュ全消去**

- Chrome / Edge: Ctrl + Shift + Del → 「キャッシュされた画像とファイル」に
  チェック → 期間「全期間」→ 「削除」

**対処 6: 別ブラウザで試す**

Chrome ダメなら Edge、Edge ダメなら Firefox 等で `http://192.168.11.200:5000/`。
これで見えるなら元のブラウザの拡張機能や設定が原因。

**対処 7: 開発者ツールで詳細エラーを確認**

F12 キーで開発者ツールを開き、Network タブでエラー詳細を確認:

| ブラウザ側エラー | 原因 | 対処 |
|---|---|---|
| `net::ERR_CONNECTION_REFUSED` | ネットワーク側 | 第 2 階層に戻る |
| `net::ERR_CACHE_MISS` | キャッシュ不整合 | 対処 5 (全消去) |
| `net::ERR_SSL_PROTOCOL_ERROR` | HTTPS を誤指定 | 対処 4 |
| `Blocked by CORS policy` | CORS 未許可 | Flask の ALLOWED_ORIGINS 確認 |
| `net::ERR_NAME_NOT_RESOLVED` | DNS 名前解決失敗 | IP アドレスで直接指定 |

### 7.6 復旧・撤退プラン

現行 Flask サーバーで致命的な問題が起きた場合、旧版に戻す:
```bash
sudo systemctl stop temperature-server
mv ~/temperature_server ~/temperature_server_broken_$(date +%s)
mv ~/temperature_server_backup_YYYYMMDD ~/temperature_server
sudo systemctl start temperature-server
```

---

## 8. 関連ドキュメント

- `outputs/README.md` — システム全体概要
- `outputs/docs/Arduino_IDE_設定ガイド.md` — ESP 側書込み手順
- `outputs/RaspberryPi_AP_Setup/ArcherT2UPlus_ドライバー導入.md` — ドライバの詳細
- `outputs/RaspberryPi_AP_Setup/Raspberry Pi DHCPAPセットアップガイド.md` — AP 構築の詳細
- `outputs/temperature_server_deploy/README.md` — Flask 展開手順書
- `outputs/temperature_server_deploy/dnsmasq_mac_reservation.md` — MAC 固定割当ガイド
- `outputs/temperature_server_full/README.md` — Flask 実装本体の README
- `outputs/temperature_server_full/docs/AUDIT_20260717.md` — 直近のコード監査結果
