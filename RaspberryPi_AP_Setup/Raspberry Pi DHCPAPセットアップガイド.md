# Raspberry Pi デュアル WiFi (wlan0=インターネット / wlan1=AP) セットアップガイド

## 目的

Raspberry Pi に **Wi-Fi を 2 系統** 持たせ、片方をインターネット側、もう片方を ESP-WROOM-02 ノード用の **アクセスポイント (AP)** にする構成です。

```
                  インターネット
                       │
                  ┌────┴────┐
                  │ ルーター │ YOUR_HOME_WIFI_SSID (家庭の Wi-Fi)
                  └────┬────┘
                  Wi-Fi (2.4GHz)
                       │
                ┌──────┴──────┐
                │ wlan0       │ (オンボード Wi-Fi, クライアントモード)
                │             │
                │  Raspberry  │
                │     Pi      │  Flask サーバ + dnsmasq + hostapd
                │             │
                │ wlan1       │ (USB ドングル: Archer T2U Plus, AP モード)
                └──────┬──────┘
                  Wi-Fi (2.4GHz / 5GHz)
                       │
              ┌────────┴────────┐
              │ ESP-WROOM-02    │ × N台
              │ DeepSleep ノード │ (SSID: YOUR_AP_SSID_HERE)
              └─────────────────┘
```

オンボード Wi-Fi (wlan0) で家のルーターに繋ぎ (= インターネット OK)、USB ドングル (wlan1) で **ESP 専用 AP** を立てます。両者は別セグメント (`192.168.x.x` vs `192.168.4.x`) なので競合しません。

> **前提:** Raspberry Pi OS Bookworm または **Trixie** (NetworkManager がデフォルト)。Bullseye の場合は dhcpcd ベースなので一部コマンドが異なります (本ガイド末尾に参考として注記)。

---

## 0. 必要なもの

| 項目 | 値 |
|---|---|
| Raspberry Pi 本体 | Pi 3B+ / 4B / 5 のいずれか (オンボード Wi-Fi 必須) |
| OS | Raspberry Pi OS Bookworm または **Trixie** (64bit / 32bit いずれも可) |
| USB Wi-Fi ドングル | TP-Link Archer T2U Plus (RTL8821AU、実機は `lsusb` で確認) |
| ドライバー | **morrownr/8821au-20210708** (v5.12.5.2、追記不要)。詳細は別ガイド「ArcherT2UPlus_ドライバー導入.md」参照 |
| 既設 Wi-Fi | SSID `YOUR_HOME_WIFI_SSID` / key `YOUR_HOME_WIFI_PASSWORD` (家庭ルーター) |
| 新規 AP | SSID `YOUR_AP_SSID_HERE` / key `YOUR_AP_PASSWORD_HERE` |

### 実証済みの動作範囲 (2026-07-12 検証)

本ガイドの手順を新規 SD カード上で通し実行し、以下まで確認済み:

- OS: Raspberry Pi OS Trixie 64bit
- カーネル: 6.12.75+rpt-rpi-v8
- ドライバー: `morrownr/8821au-20210708` v5.12.5.2
- wlan1 の `driver` シンボリックリンクが `rtl8821au` を指す (誤って `rtl8812au` を入れていないことの決定的証拠)
- hostapd: `active`、ログに `AP-ENABLED`、SSID `YOUR_AP_SSID_HERE` broadcast
- dnsmasq: `active`、DHCP range 192.168.4.2〜254 を提供
- リブート後、電源投入だけで **上記全サービスが正しい順序で自動立ち上がる** (実測: wlan1-static-ip → hostapd → dnsmasq)
- iPhone から `YOUR_AP_SSID_HERE` に接続 → **WPA2 認証 + DHCP で 192.168.4.73 割当** まで完全動作

---

## 1. 全体の作業順序

本ガイドの作業は **2段階構成** です。事前準備が完了していないと §3 以降の設定をしても効きません (NetworkManager は存在しないインターフェースを unmanaged にできない、hostapd は対象 NIC が無いと起動失敗、など)。

### 事前準備 (§3 以降を始める前に必須)

| 段階 | 内容 | 場所 |
|---|---|---|
| A | オンボード Wi-Fi (wlan0) で `YOUR_HOME_WIFI_SSID` に接続 | 本ガイドの §2-1 |
| B | USB ドングルのドライバーをインストール → `ip link` で `wlan1` が出ること | **別ガイド「ArcherT2UPlus_ドライバー導入.md」を完了させてから戻ってくる** |

### 本ガイドの作業

| 順序 | 内容 | 場所 |
|---|---|---|
| 1 | `wlan1` が NetworkManager に自動管理されないように切り離す | §3 |
| 2 | `hostapd` をインストール → `wlan1` で AP を立てる | §4 |
| 3 | `dnsmasq` をインストール → `wlan1` で DHCP サーバを立てる | §5 |
| 4 | `wlan1` に固定 IP `192.168.4.1` を設定 | §6 |
| 5 | サービス起動順を確定 + リブートで全体確認 | §7 |
| 6 | (オプション) IP フォワーディングを有効化 | §9 |

> **重要:** ドライバー未導入の状態で §3 (unmanaged 設定) や §4 (hostapd) を実行しても何も起きません。`nmcli device status` に `wlan1` の行が無ければ、まず別ガイドのドライバー導入を完了させてください。

---

## 2. 事前準備

### 2-1. オンボード Wi-Fi (wlan0) を YOUR_HOME_WIFI_SSID に接続

通常 Pi のセットアップ時に済ませているケースが多いので、すでに wlan0 でインターネットに出られていればスキップして 2-2 へ。

#### Bookworm / Trixie (NetworkManager) の場合

Raspberry Pi OS の Imager で SSID を指定していれば既に接続されています。接続プロファイル名は環境で異なる (例: `netplan-wlan0-YOUR_HOME_WIFI_SSID`、`preconfigured` 等) ので `nmcli connection show --active` で確認してください:

```bash
# 現在の active な接続プロファイル名を確認
nmcli connection show --active
```

もし未接続なら新規に接続:

```bash
sudo nmcli device wifi connect "YOUR_HOME_WIFI_SSID" \
     password "YOUR_HOME_WIFI_PASSWORD" \
     ifname wlan0 \
     name "home-wifi"

sudo nmcli connection modify "home-wifi" connection.autoconnect yes
```

確認:

```bash
nmcli device status
# wlan0  wifi  connected  <接続名>  ← 接続名は環境で異なる

# 疎通確認
ping -c 3 -I wlan0 8.8.8.8
```

### 2-1-b. wlan0 を静的 IP 化 (Pi を紛失しないため、推奨)

DHCP のままだとリブートや電源変更で IP が変わる可能性があります。SSH で管理するなら **wlan0 を静的 IP 化しておくと安全** です:

```bash
# 現在の接続プロファイル名を確認 (上のコマンドで判明済み)
CONN_NAME="<実際の接続名、例: netplan-wlan0-YOUR_HOME_WIFI_SSID>"

# 現在の DHCP IP を確認して同じ値を静的化する
CURRENT_IP=$(ip -4 addr show wlan0 | awk '/inet /{print $2}' | head -1)
GATEWAY=$(ip route show default | awk '{print $3}' | head -1)

echo "現在の IP: $CURRENT_IP"
echo "ゲートウェイ: $GATEWAY"

# 静的 IP 化
sudo nmcli connection modify "$CONN_NAME" \
    ipv4.method manual \
    ipv4.addresses "$CURRENT_IP" \
    ipv4.gateway "$GATEWAY" \
    ipv4.dns "$GATEWAY,8.8.8.8"

# 適用
sudo nmcli connection down "$CONN_NAME"
sudo nmcli connection up "$CONN_NAME"
```

`nmcli connection down` の瞬間 SSH が 1〜2 秒切れる可能性があります。切れたら同じ IP で再接続。

**リブートで永続化検証**: `sudo reboot` → 再度同じ IP で SSH 接続できることを確認。

#### Bullseye (dhcpcd + wpa_supplicant) の場合

```bash
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

追記内容:

```
country=JP
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="YOUR_HOME_WIFI_SSID"
    psk="YOUR_HOME_WIFI_PASSWORD"
    key_mgmt=WPA-PSK
}
```

```bash
sudo systemctl restart wpa_supplicant
sudo systemctl restart dhcpcd
```

### 2-2. USB ドングルのドライバーをインストール

**これが本ガイドで一番つまずきやすいポイント**です。Archer T2U Plus は Raspberry Pi OS の素の状態では認識されません (Realtek の有志ドライバーが必要)。

別ガイド **「ArcherT2UPlus_ドライバー導入.md」** の手順を完了させてください。最後に DKMS でインストール → 再起動まで進めることが必要です。

完了確認:

```bash
# USB として見えているか
lsusb | grep -i -E 'realtek|tp-link'
# 例: TP-Link Archer T2U PLUS [RTL8821AU]

# ドライバーがロードされているか
lsmod | grep -E '8812au|88x2bu|8821'
# 例: 8812au   xxxxxxx  0

# インターフェースとして wlan1 が見えるか
ip link
# wlan1: <BROADCAST,MULTICAST> ...   ← これが出ていれば OK

# nmcli からも見えるか (この時点ではまだ unmanaged にしていないので "disconnected" のはず)
nmcli device status
# wlan1  wifi  disconnected  --
```

`ip link` に `wlan1` が出ていない状態では §3 以降は無意味です。必ずこの 4 つの確認を通してから次に進んでください。

---

## 3. wlan1 を NetworkManager の管理から外す

> **前提:** §2-2 を完了し、`ip link` および `nmcli device status` で `wlan1` が見えていること。ここで `wlan1` が見えていない場合、本節の設定ファイルを作っても **何も起きません** (NetworkManager は存在しないインターフェースを unmanaged にできない)。先に §2-2 へ戻ってください。

これを設定しないと、NetworkManager が `wlan1` の管理を奪い合って **hostapd と競合し AP が立たない** ことがあります。

### Bookworm / Trixie (NetworkManager)

`/etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf` を作成:

```bash
sudo tee /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf << 'EOF'
[keyfile]
unmanaged-devices=interface-name:wlan1
EOF

# reload で新設定を反映 (restart より wlan0 の接続を切らないので安全)
sudo systemctl reload NetworkManager
```

確認:

```bash
sleep 1
nmcli device status
# wlan1  wifi  unmanaged  --  ← unmanaged になっていれば OK
```

> **`restart` ではなく `reload` を使う理由:** `restart` は NetworkManager 全体を止めて起動しなおすため、wlan0 側の SSH 接続が瞬断されます (静的 IP 化前ならリース更新で数秒程度失敗する可能性)。`reload` は設定ファイルの再読み込みだけで、既存の接続は維持されます。

### Bullseye (dhcpcd)

`/etc/dhcpcd.conf` の末尾に追記:

```
denyinterfaces wlan1
```

```bash
sudo systemctl restart dhcpcd
```

---

## 4. hostapd インストール + 設定 (wlan1 を AP 化)

```bash
sudo apt update
sudo apt install -y hostapd
```

設定ファイル `/etc/hostapd/hostapd.conf` を新規作成 (実証済み構成):

```bash
sudo tee /etc/hostapd/hostapd.conf > /dev/null << 'EOF'
interface=wlan1
driver=nl80211
ssid=YOUR_AP_SSID_HERE
country_code=JP
hw_mode=g
channel=6
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=YOUR_AP_PASSWORD_HERE
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
EOF

# passphrase を含むので他ユーザから隠す
sudo chmod 600 /etc/hostapd/hostapd.conf
```

設定要点:

| キー | 値 | 意味 |
|---|---|---|
| `interface` | wlan1 | AP として使うインターフェース |
| `driver` | nl80211 | 標準ドライバ。8821au ドライバー導入後にこれで動く |
| `ssid` | `YOUR_AP_SSID_HERE` | ESP 側コードでハードコードしたものと一致させる |
| `country_code` | JP | 必須。日本の電波法に合わせて使えるチャンネルが決まる |
| `hw_mode=g` + `channel=6` | 2.4GHz 11g | ESP-WROOM-02 は 2.4GHz のみ対応のため |
| `wpa=2` + `wpa_passphrase` | WPA2-PSK | パスフレーズはコードと一致させる |
| `wpa_pairwise=CCMP` | AES/CCMP のみ (TKIP は非推奨) | 現代的な WPA2 標準 |
| `macaddr_acl=0` | MAC 制限なし | 全 MAC 接続許容 |

`hostapd` のデフォルトコンフィグパスを設定:

```bash
# 既存 DAEMON_CONF 行があれば上書き、無ければ追記
if grep -q '^DAEMON_CONF=' /etc/default/hostapd 2>/dev/null; then
    sudo sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
else
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' | sudo tee -a /etc/default/hostapd
fi

# Debian デフォルトの起動抑止を解除 + 起動時自動起動を有効化
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
```

**現時点では start しない** (wlan1 に IP がまだ無いので、hostapd 単独では動くが後段の DHCP がまだ揃っていない)。全体を §7 で `sudo reboot` で立ち上げる。

---

## 5. dnsmasq インストール + 設定 (wlan1 で DHCP)

```bash
sudo apt install -y dnsmasq
```

`/etc/dnsmasq.d/wlan1.conf` を新規作成 (既存の `/etc/dnsmasq.conf` には触らない):

```bash
sudo tee /etc/dnsmasq.d/wlan1.conf > /dev/null << 'EOF'
interface=wlan1
dhcp-range=192.168.4.2,192.168.4.254,255.255.255.0,24h
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
EOF
```

設定要点:

| キー | 意味 |
|---|---|
| `interface=wlan1` | wlan1 側のみ DHCP を提供 (wlan0 = 既設 WiFi 側には影響しない) |
| `dhcp-range=192.168.4.2,192.168.4.254,...,24h` | 192.168.4.2 〜 254 を動的割当、24時間リース (240台まで受け入れ) |
| `dhcp-option=option:router,192.168.4.1` | クライアントのデフォルトルート = Pi 自身 |
| `dhcp-option=option:dns-server,8.8.8.8,8.8.4.4` | クライアントの DNS = Google DNS (Pi 側で DNS 転送設定なしで済む) |

> **`bind-interfaces` を指定しない理由:** デフォルト (指定なし) では dnsmasq は全 IF で listen し、interface= で指定した IF の DHCP 要求のみに応答します。`bind-interfaces` を指定すると起動時に wlan1 が上がっていないと失敗するため、systemd の起動順序に依存してしまい脆弱です。指定なしで運用するのが実証で動作確認済み。

> **`log-dhcp` を常時 ON にしない理由:** DHCP イベント (DISCOVER/OFFER/REQUEST/ACK) が全て syslog に出るため、常用ではログ量が多すぎます。トラブル切り分け時のみ `sudo sed -i '$a log-dhcp' /etc/dnsmasq.d/wlan1.conf && sudo systemctl restart dnsmasq` で足すのが実用的。

> **MAC アドレス固定割当が欲しい場合** (端末番号を IP で識別したいなど):
>
> ```
> dhcp-host=AA:BB:CC:11:22:33,esp8266-01,192.168.4.21
> dhcp-host=AA:BB:CC:11:22:34,esp8266-02,192.168.4.22
> ```
>
> ESP の MAC は `WiFi.macAddress()` でシリアルに出させて控えておくと楽。

インストール時点で dnsmasq は自動 enable + active になっています (Debian デフォルト)。上記 config を配置したら反映のため再起動:

```bash
sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq --no-pager | head -10
```

期待するログ (`journalctl -u dnsmasq -n 10 --no-pager`):

```
dnsmasq-dhcp: DHCP, IP range 192.168.4.2 -- 192.168.4.254, lease time 1d
```

---

## 6. wlan1 に固定 IP (192.168.4.1) を割り当て

Bookworm/Trixie では NetworkManager で wlan1 を unmanaged にした (§3) ため、別の管理層で IP を付ける必要があります。実証済みの方式は **systemd unit で起動時に `ip` コマンドを叩く**です。

### Bookworm / Trixie (systemd unit 方式) — 実証済み

`/etc/systemd/system/wlan1-static-ip.service` を作成:

```bash
sudo tee /etc/systemd/system/wlan1-static-ip.service > /dev/null << 'EOF'
[Unit]
Description=Setup wlan1 Static IP for AP Mode
After=sys-subsystem-net-devices-wlan1.device
Requires=sys-subsystem-net-devices-wlan1.device

[Service]
Type=oneshot
ExecStart=/sbin/ip addr flush dev wlan1
ExecStart=/sbin/ip addr add 192.168.4.1/24 dev wlan1
ExecStart=/sbin/ip link set wlan1 up
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wlan1-static-ip.service
```

設定の要点:

| 要素 | 意味 |
|---|---|
| `After` + `Requires` = `sys-subsystem-net-devices-wlan1.device` | wlan1 デバイスが systemd に認識されてから実行 (ドライバ ロード → デバイス生成のタイミングに追従) |
| `Type=oneshot` + `RemainAfterExit=yes` | 一度実行して終了、以降 `active (exited)` を保つ |
| `ip addr flush` を先頭に | 古い IP が残っていた場合の二重割当エラー予防 |
| `Before=hostapd.service` は指定しない | 実測で systemd の自然順序 (wlan1-static-ip → hostapd → dnsmasq) で動くため不要 |

### 現時点では start しない

Phase 4-3 と同じく、この unit は **enable だけで start はしません**。§7 の `sudo reboot` で全体一括で立ち上がるのを確認します。

### Bullseye — dhcpcd.conf で割り当てる方式 (参考)

Bullseye では NetworkManager ではなく dhcpcd が主流のため:

```bash
sudo tee -a /etc/dhcpcd.conf << 'EOF'

interface wlan1
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF

sudo systemctl restart dhcpcd
```

---

## 7. リブートで永続化を検証

すべてのユニット (`wlan1-static-ip`、`hostapd`、`dnsmasq`) は §4〜§6 の作業で `enable` 済みです。追加の enable コマンドは不要。ここで一度リブートして、**電源投入だけで自動立ち上がる** ことを検証します。

```bash
sudo reboot
```

再起動後 30〜60 秒待って、PC 側 PowerShell から SSH 再接続:

```powershell
ssh pi@<wlan0のIP>
# 例: ssh pi@192.168.11.200
```

### リブート後の一括確認 (Pi 側で実行)

```bash
echo "=== 1. wlan0 (既設 WiFi 経由インターネット、静的 IP) ==="
ip -4 addr show wlan0 | grep inet
ping -c 2 -W 2 -I wlan0 8.8.8.8 2>/dev/null | tail -2

echo ""
echo "=== 2. wlan1 (AP 側、静的 IP 192.168.4.1) ==="
ip -4 addr show wlan1

echo ""
echo "=== 3. NM から見た wlan1 (unmanaged 継続) ==="
nmcli device status | grep wlan1

echo ""
echo "=== 4. wlan1-static-ip.service ==="
systemctl is-active wlan1-static-ip.service

echo ""
echo "=== 5. hostapd (AP-ENABLED 確認) ==="
systemctl is-active hostapd.service
sudo journalctl -u hostapd -n 5 --no-pager | grep -E 'AP-ENABLED|COUNTRY|state'

echo ""
echo "=== 6. dnsmasq (DHCP range) ==="
systemctl is-active dnsmasq.service
sudo journalctl -u dnsmasq -n 5 --no-pager | grep -iE 'DHCP.*range'
```

### 期待する結果 (全項目クリアで永続化成功)

| 項目 | 期待値 |
|---|---|
| wlan0 IP | 静的 IP (例: 192.168.11.200/24) |
| wlan0 → インターネット | ping 応答あり |
| wlan1 IP | 192.168.4.1/24 |
| wlan1 NM 状態 | `unmanaged` |
| wlan1-static-ip.service | `active` (oneshot なので `active (exited)`) |
| hostapd.service | `active`、ログに `AP-ENABLED` |
| dnsmasq.service | `active`、`DHCP, IP range 192.168.4.2 -- 192.168.4.254, lease time 1d` |

### 実測された起動順序 (参考)

タイムスタンプ実測 (kernel 6.12.75、boot からの秒数):

```
07:56:23  wlan1-static-ip.service 開始 → 完了 (1秒)
07:56:30  hostapd 起動 → UNINITIALIZED → COUNTRY_UPDATE → ENABLED → AP-ENABLED
07:56:35  dnsmasq 起動 (DHCP range 192.168.4.2-254 有効化)
```

明示的な依存関係を書かなくても、systemd の自然順序で正しく並ぶことが実測で確認済みです。

---

## 8. クライアント接続テスト

### 手軽な確認: スマホから接続

ESP-WROOM-02 のスケッチを書き込む前に、スマホから AP に接続できることを確認しておくと問題切り分けが楽です。

1. スマホの Wi-Fi 設定で **`YOUR_AP_SSID_HERE`** をタップ
2. パスフレーズ **`YOUR_AP_PASSWORD_HERE`** を入力
3. 接続完了 → 192.168.4.X の IP が振られる

### Pi 側で接続を確認

```bash
# DHCP リースファイル
sudo cat /var/lib/misc/dnsmasq.leases

# 現在接続中のステーション (電波レベル、接続時間、送受信バイト数)
sudo iw dev wlan1 station dump | grep -E 'Station|signal|tx bytes|rx bytes'

# hostapd の直近ログ (STA 接続イベント)
sudo journalctl -u hostapd --since "5 minutes ago" --no-pager | grep -E 'STA|CONNECTED|associated'

# DHCP プロトコルの流れをリアルタイム監視 (Ctrl+C で終了)
sudo journalctl -u dnsmasq -f
```

### 実証済みの成功パターン (iPhone 接続時の記録)

```
=== 現在の DHCP リース ===
1784073276 fa:a1:95:d3:90:fe 192.168.4.73 iPhone 01:fa:a1:95:d3:90:fe

=== dnsmasq の DHCP イベントログ ===
dnsmasq-dhcp: DHCPDISCOVER(wlan1) fa:a1:95:d3:90:fe
dnsmasq-dhcp: DHCPOFFER(wlan1) 192.168.4.73 fa:a1:95:d3:90:fe
dnsmasq-dhcp: DHCPREQUEST(wlan1) 192.168.4.73 fa:a1:95:d3:90:fe
dnsmasq-dhcp: DHCPACK(wlan1) 192.168.4.73 fa:a1:95:d3:90:fe iPhone

=== hostapd の STA イベント ===
hostapd[XXXX]: wlan1: STA fa:a1:95:d3:90:fe IEEE 802.11: associated
hostapd[XXXX]: wlan1: STA fa:a1:95:d3:90:fe WPA: pairwise key handshake completed (RSN)
```

**判定**: DHCPACK まで通り、hostapd に `pairwise key handshake completed` が出れば **AP + DHCP の完全動作** が確認できます。

### ESP-WROOM-02 の接続確認

ESP 側のスケッチ (STEP 2) を書き込んで電源投入すると、シリアルログに次のような出力が出るはず:

```
[WiFi] connecting to "YOUR_AP_SSID_HERE" ...
[WiFi] connected ip=192.168.4.XX rssi=-58 dBm
[POST] HTTP 200
```

Pi 側の dnsmasq ログには対応する DHCPACK が、hostapd ログには対応する STA-CONNECTED イベントが記録されます。

---

## 9. (オプション) IP フォワーディング = ESP から外部に出られるように

ESP がインターネットへ抜ける必要がない (Flask への送信のみ) なら、このセクションは飛ばして OK です。NTP 取りに行きたい等で必要になったら設定します。

```bash
# IP フォワーディングを有効化 (永続化)
sudo sed -i 's/^#net.ipv4.ip_forward=1/net.ipv4.ip_forward=1/' /etc/sysctl.conf
sudo sysctl -w net.ipv4.ip_forward=1

# wlan0 を経由した NAT を設定
sudo apt install -y iptables iptables-persistent
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan1 -o wlan0 -j ACCEPT
sudo iptables -A FORWARD -i wlan0 -o wlan1 -m state --state RELATED,ESTABLISHED -j ACCEPT

# 永続化
sudo netfilter-persistent save
```

---

## 10. wlan0 と wlan1 のコンフリクト対策チェックリスト

両者が衝突する典型パターンと対策:

| 問題 | 対策 |
|---|---|
| NetworkManager が wlan1 を奪う | `99-unmanaged-wlan1.conf` で除外 (本ガイド §3) |
| wpa_supplicant が wlan1 にも attach | `dhcpcd.conf` で `denyinterfaces wlan1` (Bullseye) |
| 同じセグメントが衝突 | ホーム Wi-Fi が `192.168.0.x` なら `192.168.4.x` を AP 側に。被らない値を選ぶ |
| デフォルトルートが wlan1 になる | `dnsmasq` 設定で wlan1 側に gateway を撒くが、Pi 自身の経路は変えない |
| DNS が AP の DNS に向く | Pi は `/etc/resolv.conf` で `127.0.0.53` (systemd-resolved) を使うので影響なし |

---

## 11. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| **`hostapd` 起動失敗 `Operation not permitted` (最頻ハマリ)** | **ドライバー選定ミス**: Archer T2U Plus (RTL8821AU) に `morrownr/8812au-20210820` (RTL8812AU 用) を導入している。全対処 (NM unmanaged、rfkill、regulatory JP) を試しても消えない | `readlink /sys/class/net/wlan1/device/driver` を確認: 末尾が `rtl8812au` なら誤リポジトリ。`morrownr/8821au-20210708` に切り替える (別ガイド「ArcherT2UPlus_ドライバー導入.md」§13 参照) |
| `hostapd` 起動失敗 `Could not get state` | wlan1 が NetworkManager に握られたまま | `99-unmanaged-wlan1.conf` を再確認、`sudo systemctl reload NetworkManager` |
| `hostapd` 起動失敗 `nl80211: Could not configure driver mode` | 上と同じドライバー選定ミスの症状 (別ログ表現) | 上と同じ対処 |
| クライアントが繋がらない | 周波数不一致 (5GHz指定だがESPは2.4GHzのみ) | `hw_mode=g` `channel=6` のままで OK |
| 繋がるが IP がもらえない | dnsmasq が起動していない / wlan1 に IP が付いていない | `sudo systemctl status dnsmasq` + `ip -4 addr show wlan1` で 192.168.4.1 を確認 |
| 突然 wlan1 が消える | USB の電源ドロップ | セルフパワー USB ハブ経由にする |
| インターネットに出られなくなった | wlan0 の経路が消えた | `sudo nmcli connection up <接続名>` で再接続 |
| `Could not initialise hostapd interface ... (could not configure)` | country_code 未設定 | `country_code=JP` を hostapd.conf に追加 |
| AP は立ったが ESP の rssi が -85 以下 | アンテナ位置 / 障害物 | T2U Plus の延長ケーブルでアンテナを別の場所に |
| リブート後 hostapd が inactive | wlan1 が起動時に見えていない可能性 | `journalctl -u wlan1-static-ip.service` で失敗理由を確認 (`sys-subsystem-net-devices-wlan1.device` の待受でタイムアウトなど) |

---

## 12. 構築後の運用メモ

- **ログの場所**: `journalctl -u hostapd` / `journalctl -u dnsmasq` / `journalctl -u wlan1-static-ip.service`
- **DHCP リース履歴**: `/var/lib/misc/dnsmasq.leases` (フォーマット: `<expiry_epoch> <mac> <ip> <hostname> <client_id>`)
- **現在接続中のクライアント**: `sudo iw dev wlan1 station dump` (電波レベル、送受信バイト数含む)
- **Pi のリブート後の自動起動**: §4〜§6 で全ユニットを `enable` 済みなら、起動時に自動で立ち上がる (実測起動順は §7 参照)
- **AP のチャンネル変更**: 周辺 Wi-Fi が混雑しているなら `channel=11` に変えて `sudo systemctl restart hostapd`
- **hostapd config 変更後**: `sudo systemctl restart hostapd` で反映 (**config は /etc/hostapd/hostapd.conf**、Phase 3 で使った /tmp/hostapd-test.conf ではない)
- **MAC 固定割当を増やす**: `/etc/dnsmasq.d/wlan1.conf` に `dhcp-host=...` 行を追加して `sudo systemctl restart dnsmasq`
- **ドライバー整合性の定期確認**: kernel 更新後は `readlink /sys/class/net/wlan1/device/driver` が `rtl8821au` を指していることを確認 (DKMS で自動再ビルドされているはずだが念のため)
- **ドライバー導入ガイドの `readlink` チェック**: 定期的に driver シンボリックリンクが期待通りかを確認する習慣をつけると、ハマる前に気付ける

---

## 13. 関連ドキュメント

- 「ArcherT2UPlus_ドライバー導入.md」 — wlan1 として認識させる前段の作業
- 「電池駆動配線ガイド.md」 — ESP 側のハード
- 「ESP8266_DS18B20_HTTPPOST.ino のブログ解説.md」 — ESP 側のソフト
