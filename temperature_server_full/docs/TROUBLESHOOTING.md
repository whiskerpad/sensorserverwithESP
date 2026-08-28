# 🔧 トラブルシューティング完全ガイド

**このガイドは、実際の問題発生時の診断・解決手順を示します**

---

## 診断のフロー

```
問題が発生した
  ↓
【第1階層】ハードウェア認識
  ├─ USB WiFi ドングルが見えるか
  ├─ Raspberry Pi が起動しているか
  └─ SSH で接続できるか
  
  すべて OK → 【第2階層】へ
  
【第2階層】ネットワークインターフェース
  ├─ wlan0 が UP しているか
  ├─ wlan1 が UP しているか
  ├─ IP アドレスが割り当てられているか
  └─ ping が疎通するか
  
  すべて OK → 【第3階層】へ
  
【第3階層】サービス動作
  ├─ hostapd が起動しているか
  ├─ dnsmasq が起動しているか
  ├─ Flask が起動しているか
  └─ エラーログに異常はないか
  
  すべて OK → 【第4階層】へ
  
【第4階層】アプリケーション動作
  ├─ localhost テストが成功するか
  ├─ 192.168.4.1 テストが成功するか
  ├─ ESP32 が接続しているか
  └─ データが保存されているか
```

---

## 問題別解決方法

### 🔴 Issue 1: Raspberry Pi に SSH で接続できない

#### 症状
```
$ ssh pi@raspberrypi.local
ssh: Could not resolve hostname raspberrypi.local
```

#### 診断

```bash
# 同じネットワークに接続しているか確認
ping 192.168.1.1  # ゲートウェイ

# Raspberry Pi が起動しているか確認（ネットワークから見える）
arp-scan --localnet | grep -i "raspberry"

# または nmap でスキャン
nmap -p 22 192.168.11.0/24
```

#### 解決方法

**方法 A：IP アドレスで直接接続**
```bash
ssh pi@192.168.11.200
# IP アドレスは自分の環境に合わせて変更
```

**方法 B：ホスト名解決の確認**
```bash
# Windows (PowerShell)
Resolve-DnsName raspberrypi.local

# Mac/Linux
nslookup raspberrypi.local
```

**方法 C：Raspberry Pi をリセット**
```bash
# モニターとキーボードで直接接続して
# OS を再インストール
```

---

### 🔴 Issue 2: wlan1 が認識されない

#### 症状
```
$ ip link show
1: lo: ...
2: eth0: ...
3: wlan0: ...
# wlan1 が見当たらない！
```

#### 診断

```bash
# USB ドングルが認識されているか確認
lsusb | grep -i "tp-link\|2357:0120"

# ドライバがインストールされているか確認
dkms status | grep -i 8821

# ドライバが読み込まれているか確認
lsmod | grep -i 8821

# ドングルのデバイスが見える
ls -la /sys/bus/usb/devices/*/idVendor
```

#### 解決方法

**症状 A：lsusb に TP-Link が見えない**
```bash
# USB ケーブルを確認（別のポートに挿す）
# Raspberry Pi を再起動
sudo reboot
```

**症状 B：lsusb に見えるが、dkms status に見えない**
```bash
# ドライバ再インストール
cd /tmp
git clone https://github.com/morrownr/8821au-20210708.git
cd 8821au-20210708
sudo bash install-driver.sh

# インストール完了後
dkms status
# 出力: 8821au, 20210708, 6.1.0-xxx, aarch64: installed

# 再起動
sudo reboot
```

**症状 C：dkms に見えるが、lsmod に見えない（読み込まれていない）**
```bash
# 手動で読み込み
sudo modprobe 8821au

# 確認
lsmod | grep 8821au

# 再起動
sudo reboot
```

---

### 🔴 Issue 3: wlan1 の IP アドレスが 192.168.4.1 ではない（別のWiFiネットワークに接続されている）

#### 症状
```
$ ip addr show wlan1
4: wlan1: <BROADCAST,MULTICAST,UP,LOWER_UP>
    inet 172.17.5.42/24 scope global wlan1  # ← 違う！APモードではない
    # または
    inet 192.168.1.93/24 scope global wlan1  # ← 違う！
```

**追加症状：**
- ESP32からのPOSTが受信されない
- NetworkManagerがwlan1を管理している（`nmcli device status | grep wlan1`で`managed`と表示される）

#### 診断

```bash
# wlan1のIPアドレスを確認
ip addr show wlan1 | grep "inet "

# NetworkManagerがwlan1を管理しているか確認
nmcli device status | grep wlan1
# 出力が "wlan1 wifi managed" の場合は問題あり

# NetworkManagerのログを確認（wlan1がWiFiに接続しようとしているか）
journalctl -u NetworkManager --since '1 hour ago' | grep -i wlan1

# free_wifiサービスが動作しているか確認（原因の可能性）
systemctl status guest2-repeater.service

# dhcpcd 設定を確認
cat /etc/dhcpcd.conf | tail -20

# wlan1 の設定が存在するか確認
grep -A 3 "interface wlan1" /etc/dhcpcd.conf
```

#### 原因

**主な原因：NetworkManagerがwlan1を管理している**

1. NetworkManagerがwlan1を管理している場合、他のサービス（例：`free_wifi`の再接続処理）がwlan0を操作（`rfkill block/unblock wlan0`）すると、NetworkManagerがWiFiインターフェースの状態変化を検知します。
2. NetworkManagerがwlan1も再スキャンし、既知のWiFiネットワーク（過去に接続したことがある）に自動接続してしまいます。
3. 結果として、wlan1がAPモード（192.168.4.1）から別のWiFiネットワークに切り替わります。

**確認方法：**
```bash
# NetworkManagerのログでwlan1の接続試行を確認
journalctl -u NetworkManager | grep -i "wlan1.*associating\|wlan1.*completed"
# 出力例：
# device (wlan1): supplicant interface state: scanning -> associating
# device (wlan1): supplicant interface state: associating -> completed
# dhcp4 (wlan1): state changed new lease, address=172.17.5.42
```

#### 解決方法

**方法 A：NetworkManagerがwlan1を管理しないように設定（推奨）**

```bash
# 1. NetworkManager設定ディレクトリを作成
sudo mkdir -p /etc/NetworkManager/conf.d

# 2. wlan1を管理対象外にする設定ファイルを作成
sudo bash -c 'cat > /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf << EOF
[keyfile]
unmanaged-devices=interface-name:wlan1
EOF'

# 3. NetworkManagerをリロード
sudo systemctl reload NetworkManager

# 4. 確認
nmcli device status | grep wlan1
# 出力が "wlan1 wifi unmanaged" になればOK

# 5. wlan1をAPモードに復旧
sudo ip addr flush dev wlan1
sudo ip addr add 192.168.4.1/24 dev wlan1
sudo ip link set wlan1 up

# 6. hostapdを再起動
sudo systemctl restart hostapd
```

**方法 B：wlan1-static-ip.service を使用（自動設定）**

```bash
# サービスが有効化されているか確認
systemctl is-enabled wlan1-static-ip.service

# 有効化されていない場合は有効化
sudo systemctl enable wlan1-static-ip.service
sudo systemctl restart wlan1-static-ip.service

# 確認
sudo systemctl status wlan1-static-ip.service
ip addr show wlan1 | grep "inet 192.168.4.1"
```

**方法 C：dhcpcd.conf を編集（従来の方法）**

```bash
# dhcpcd.conf を編集
sudo nano /etc/dhcpcd.conf

# 以下を末尾に追加（既存の場合は修正）
# ───────────────────────────────────
# interface wlan1
# static ip_address=192.168.4.1/24
# nohook wpa_supplicant
# ───────────────────────────────────

# 保存 (Ctrl+O, Enter, Ctrl+X)

# dhcpcd を再起動
sudo systemctl restart dhcpcd

# 確認
ip addr show wlan1
```

---

### 🔴 Issue 4: hostapd が起動しない

#### 症状
```
$ sudo systemctl status hostapd
● hostapd.service
    Active: inactive (dead) ✗
```

#### 診断

```bash
# エラーログを確認
sudo journalctl -u hostapd -n 50

# 手動で起動してエラーを見る
sudo hostapd -d /etc/hostapd/hostapd.conf
```

#### よくあるエラーと解決方法

**エラー 1: wlan1: interface state UNINITIALIZED**
```
原因：wlan1 インターフェースが DOWN している

解決：
sudo ip link set wlan1 up
sudo systemctl restart hostapd
```

**エラー 2: wlan1: nl80211: Failed to set interface...**
```
原因：別のプロセスが wlan1 を使用している

解決：
# wpa_supplicant を無効化
sudo systemctl stop wpa_supplicant
sudo systemctl disable wpa_supplicant

# dhcpcd の設定で wpa_supplicant をフック
sudo nano /etc/dhcpcd.conf
# interface wlan1 セクションに以下を追加：
# nohook wpa_supplicant

sudo systemctl restart hostapd
```

**エラー 3: /etc/hostapd/hostapd.conf: No such file**
```
原因：設定ファイルが存在しない

解決：
# 設定ファイルを作成
sudo nano /etc/hostapd/hostapd.conf

# 必要な内容を入力：
interface=wlan1
driver=nl80211
ssid=YOUR_AP_SSID_HERE
...
```

---

### 🔴 Issue 5: ESP32 が AP に接続できない

#### 症状
```
ESP32 ログ：
WiFi: Scanning for networks...
WiFi: YOUR_AP_SSID_HERE found
WiFi: Connecting to YOUR_AP_SSID_HERE...
❌ Connection failed (error code: -1)
```

#### 診断

```bash
# AP が正常にブロードキャストしているか確認
sudo iw dev wlan1 info

# クライアントは接続していないか確認
sudo iw dev wlan1 station dump
# 出力がなければ接続していない

# WiFi チャンネルを確認
iwlist wlan1 channel
```

#### 解決方法

**原因 1：WiFi パスワードが間違っている**
```bash
# hostapd.conf を確認
cat /etc/hostapd/hostapd.conf | grep wpa_passphrase
# デフォルト: YOUR_AP_PASSWORD_HERE

# ESP32 コード内のパスワードを確認・修正
```

**原因 2：SSID が違っている**
```bash
# hostapd.conf のSSID を確認
cat /etc/hostapd/hostapd.conf | grep "^ssid="
# デフォルト: YOUR_AP_SSID_HERE

# ESP32 コード内の SSID を確認・修正
```

**原因 3：チャンネルが干渉している**
```bash
# 別のチャンネルに変更してテスト
sudo nano /etc/hostapd/hostapd.conf
# channel=1  (または 6, 11 に変更)

sudo systemctl restart hostapd

# ESP32 から再接続試行
```

---

### 🔴 Issue 6: ESP32 は接続しているが、Flask にデータが届かない

#### 症状
```
ESP32 ログ：✓ Connected to YOUR_AP_SSID_HERE
            ✓ POST /api/temperature → HTTP 201

Flask ログ：# POST リクエストが見当たらない
```

#### 診断

```bash
# Flask が 0.0.0.0:5000 でリッスンしているか確認
sudo netstat -tlnp | grep 5000

# Flask ログを確認
sudo journalctl -u temperature-server -n 50

# Flask が起動しているか確認
sudo systemctl status temperature-server

# iptables ルールを確認
sudo iptables -L -n
```

#### 解決方法

**原因 1：Flask が localhost でのみリッスン**
```python
# config.py を確認
FLASK_HOST = '0.0.0.0'  # ✓ 正解
# または
FLASK_HOST = '127.0.0.1'  # ✗ 間違い！

# 修正後は再起動
sudo systemctl restart temperature-server
```

**原因 2：iptables ルールが設定されていない**
```bash
# iptables ルールを確認
sudo iptables -L FORWARD -n | grep wlan

# NAT ルールを確認
sudo iptables -t nat -L POSTROUTING -n | grep MASQUERADE

# ルールがない場合は追加
sudo iptables -A FORWARD -i wlan1 -o wlan0 -j ACCEPT
sudo iptables -A FORWARD -i wlan0 -o wlan1 -m state --state RELATED,ESTABLISHED -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE

# 永続化
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

**原因 3：Flask が起動していない**
```bash
# サービスを再起動
sudo systemctl restart temperature-server

# 確認
sudo systemctl status temperature-server

# エラーが出ている場合
sudo journalctl -u temperature-server -n 100
```

---

### 🔴 Issue 7: ローカルホストテストは成功するが、192.168.4.1 テストが失敗

#### 症状
```bash
$ curl http://127.0.0.1:5000/api/status
✓ Success

$ curl http://192.168.4.1:5000/api/status
✗ Connection refused / Timeout
```

#### 診断

```bash
# Flask が起動しているか確認
sudo systemctl status temperature-server

# 192.168.4.1 にアクセス可能か確認
ping 192.168.4.1

# ファイアウォール設定を確認
sudo iptables -L INPUT -n

# TCP 5000 ポートが見える
sudo netstat -tlnp | grep 5000
```

#### 解決方法

**最も一般的な原因：Flask の バインドアドレス**
```python
# ❌ 間違い
app.run(host='127.0.0.1', port=5000)  # localhost のみ

# ✓ 正解
app.run(host='0.0.0.0', port=5000)    # すべてのインターフェース

# または config.py で
FLASK_HOST = '0.0.0.0'
```

---

### 🔴 Issue 8: health check による不意の AP 再起動

#### 症状
```
定期的に ESP32 が切れる
エラーコード：-11 (connection refused)

ログに見える：
"WiFi health: warning"
"AP is not running, attempting to restart..."
```

#### 診断

```bash
# health_check が実行されているか確認
sudo journalctl -u temperature-server | grep "health\|AP is not"

# iw コマンドが見つかるか確認
which iw
# /usr/sbin/iw が返ってくれば OK
```

#### 解決方法

**方法 A：health check を無効化（推奨：開発時）**
```python
# services/background_tasks.py を編集
# self.start_wifi_health_check() をコメントアウト

def start(self):
    self.start_memory_monitor()
    # self.start_wifi_health_check()  ← コメント
    self.start_log_cleanup()

sudo systemctl restart temperature-server
```

**方法 B：iw コマンドのパスを修正（推奨：本番時）**
```python
# services/wifi_manager.py を確認
# subprocess.run(['iw', ...]) → subprocess.run(['/usr/sbin/iw', ...])

# すべて確認
grep -n "subprocess.run.*\['iw'" services/wifi_manager.py

# フルパスに修正
sed -i "s/\['iw'/['\/usr\/sbin\/iw'/g" services/wifi_manager.py

sudo systemctl restart temperature-server
```

---

## 系統的なトラブルシューティング

### テンプレート：問題の原因を特定する

```bash
#!/bin/bash
# 診断スクリプト

echo "=== WiFi ドングル ==="
lsusb | grep -i "tp-link\|2357"

echo "=== ドライバ ==="
dkms status | grep 8821

echo "=== インターフェース ==="
ip link show | grep wlan

echo "=== IP アドレス ==="
ip addr show wlan0
ip addr show wlan1

echo "=== ルーティング ==="
ip route

echo "=== ファイアウォール ==="
sudo iptables -L FORWARD -n

echo "=== サービス ==="
sudo systemctl status hostapd
sudo systemctl status dnsmasq
sudo systemctl status temperature-server

echo "=== 接続テスト ==="
curl -s http://127.0.0.1:5000/api/status | head -20
curl -s http://192.168.4.1:5000/api/status | head -20

echo "=== クライアント接続 ==="
sudo iw dev wlan1 station dump

echo "=== ログ ==="
sudo journalctl -u temperature-server -n 10
```

---

## サポートが必要な場合

詳細なログを収集してから Issue を作成してください：

```bash
# ログ収集スクリプト
cat > /tmp/collect_logs.sh << 'EOF'
#!/bin/bash

echo "=== System Info ==="
uname -a

echo "=== WiFi Info ==="
lsusb | grep -i "tp-link"
dkms status
ip link show
ip addr show

echo "=== Service Status ==="
sudo systemctl status hostapd
sudo systemctl status dnsmasq
sudo systemctl status temperature-server

echo "=== Logs ==="
sudo journalctl -u temperature-server -n 100
sudo journalctl -u hostapd -n 50
sudo journalctl -u dnsmasq -n 50

echo "=== Flask Test ==="
curl -s http://127.0.0.1:5000/api/status

echo "=== Network Test ==="
curl -s http://192.168.4.1:5000/api/status
EOF

bash /tmp/collect_logs.sh > ~/temperature-debug.log
# このファイルを Issue に添付
```

---

**最後に更新**: 2025年12月24日
