# Raspberry Pi wlan0 静的 IP → DHCP 化ガイド

作成: 2026-08-13
対象: 開発時に wlan0 (LAN 側 STA) に静的 IP を割り当てていた Pi
目的: Tailscale 導入後は LAN IP に依存しなくなったので、現地の別ルーター
      (ゲスト WiFi・別現場・出張先のホテルテザリング等) にそのまま繋がる
      構成に戻す

⚠️ **wlan1 (192.168.4.1 = ESP 用 AP) は絶対に触らない。** 本ガイドは wlan0 のみ対象。

---

## 0. なぜ DHCP に戻すか

- **開発時**: LAN IP を固定して `ssh pi@192.168.11.200` で毎回同じアドレスから入りたかった
- **現在**: Tailscale で `ssh pi@takemetothehospital` または `ssh pi@100.x.y.z` が
  どこからでも通るので、LAN IP は変わっても支障なし
- **メリット**:
  - 現地の任意のルーター (192.168.1.x / 10.0.0.x / 172.16.x.x 等) で即接続
  - ホテル・喫茶店の WiFi でも DHCP なので設定変更不要
  - LAN 環境ごとに `dhcpcd.conf` を書換える手間ゼロ

## 1. 事前確認

Pi bash で以下を実行して、**どちらの機構で静的 IP を設定しているか** を確認:

```bash
# ネットワーク管理サービスの状態
systemctl is-active NetworkManager dhcpcd 2>&1

# NetworkManager 側の接続 (Trixie/Bookworm デフォルト)
nmcli -t -f NAME,DEVICE,TYPE con show 2>/dev/null | grep -i wifi

# dhcpcd 側の静的定義 (旧 Raspbian デフォルト)
grep -A 5 "^interface wlan0" /etc/dhcpcd.conf 2>/dev/null

# 現在の wlan0 IP と経路
ip -4 addr show wlan0
ip -4 route | grep default
```

**判定**:

| 状態 | 使っている機構 | 対処セクション |
|---|---|---|
| `NetworkManager active` かつ `dhcpcd inactive/inexistent` | NetworkManager (nmcli) | §2 |
| `dhcpcd active` かつ `/etc/dhcpcd.conf` に `interface wlan0` + `static ip_address=...` | dhcpcd | §3 |
| 両方 active | 混在 (稀) | まず NetworkManager を優先確認、次に dhcpcd |

Trixie 標準は **NetworkManager** です。

## 2. NetworkManager 経由の場合

### 2.1 現在の接続名を特定

```bash
nmcli -t -f NAME,DEVICE con show | grep wlan0
```

出力例:
```
preconfigured:wlan0
```
または SSID 名 (`MyHomeWiFi:wlan0` など) が出る。この左側の名前が接続名。

### 2.2 IPv4 メソッドを auto (DHCP) に変更

```bash
# 上で取得した接続名を CON_NAME に代入 (例: "preconfigured")
CON_NAME="preconfigured"

# 現在の設定をバックアップ (表示保存)
nmcli con show "$CON_NAME" | tee ~/nmcli_backup_$(date +%Y%m%d_%H%M).txt

# IPv4 を DHCP に、固定アドレスとゲートウェイと DNS をクリア
sudo nmcli con modify "$CON_NAME" ipv4.method auto
sudo nmcli con modify "$CON_NAME" ipv4.addresses ""
sudo nmcli con modify "$CON_NAME" ipv4.gateway ""
sudo nmcli con modify "$CON_NAME" ipv4.dns ""

# 接続を再適用
sudo nmcli con down "$CON_NAME" && sudo nmcli con up "$CON_NAME"

# 新しい IP を確認 (数秒待つ)
sleep 5
ip -4 addr show wlan0
```

## 3. dhcpcd 経由の場合

### 3.1 `/etc/dhcpcd.conf` を編集

```bash
# バックアップ
sudo cp /etc/dhcpcd.conf /etc/dhcpcd.conf.static-backup.$(date +%Y%m%d_%H%M)

# 該当行をコメントアウト (interface wlan0 から次の空行まで)
sudo sed -i '/^interface wlan0/,/^$/{s/^/# /}' /etc/dhcpcd.conf

# 反映
sudo systemctl restart dhcpcd

# 新しい IP を確認
sleep 5
ip -4 addr show wlan0
```

sed が意図通り動いたか確認:
```bash
grep -A 5 "wlan0" /etc/dhcpcd.conf
```
先頭に `#` が付いていれば OK。もし複数の `interface wlan0` ブロックがあると
1 個目しかコメントアウトされない場合があるので目視確認推奨。

## 4. 動作確認

### 4.1 LAN 側新 IP の確認

```bash
ip -4 addr show wlan0 | grep inet
```
`192.168.x.y/24 ... dynamic ...` のように **dynamic** の記載があれば DHCP 化成功。

### 4.2 Tailscale 経由でアクセスできるか (別 PC から)

```powershell
# Windows PowerShell から
ssh pi@100.x.x.x             # ← 自分の Pi の Tailscale IP
# または MagicDNS 有効なら
ssh pi@takemetothehospital
```

これで入れれば、LAN 側 IP が変わっても常に到達できることを実証済み。

### 4.3 wlan1 (AP) は無事か

```bash
ip -4 addr show wlan1
```
`192.168.4.1/24` のままなら OK。ESP センサーも影響なし。

### 4.4 別ルーターに繋いでみる (現地で)

Pi の SD を持って別の LAN 環境 (ホテル・別現場) に移動:
1. その LAN の SSID/パスワードを事前に NetworkManager に設定しておく
2. Pi 起動 → 自動接続 → DHCP で IP 取得
3. Windows PC から Tailscale 経由で SSH → 動作確認

## 5. ロールバック (元の静的 IP に戻したい場合)

### 5.1 NetworkManager 経由

```bash
CON_NAME="preconfigured"
sudo nmcli con modify "$CON_NAME" ipv4.method manual \
    ipv4.addresses 192.168.11.200/24 \
    ipv4.gateway 192.168.11.1 \
    ipv4.dns "8.8.8.8 1.1.1.1"
sudo nmcli con down "$CON_NAME" && sudo nmcli con up "$CON_NAME"
```
(IP・ゲートウェイ・DNS は元環境に合わせて書換え)

### 5.2 dhcpcd 経由

バックアップから復元:
```bash
sudo cp /etc/dhcpcd.conf.static-backup.<日付> /etc/dhcpcd.conf
sudo systemctl restart dhcpcd
```

## 6. スクリプトによる自動実行

上記手順を自動化した `scripts/release_static_ip.sh` を用意。
NetworkManager と dhcpcd を自動判別、バックアップ取得、非対話で実行。

```bash
# Pi bash
cd /home/pi/<公開リポジトリ配置先>
sudo bash scripts/release_static_ip.sh
```

詳細はスクリプト冒頭のコメント参照。

## 7. 注意事項

- **SSH セッション経由での実行時**: `nmcli con down/up` を実行するとセッションが
  切れる。復旧は Tailscale (`ssh pi@100.x.y.z`) 経由で入れば OK。
  もし Tailscale も切れてしまった (稀) 場合は物理コンソール (HDMI + キーボード) から復旧。
- **wlan1 の設定**: このガイドは wlan0 のみ変更。hostapd + dnsmasq に依存する
  wlan1 = 192.168.4.1 は絶対に触らない (触ると ESP センサーの POST が停止する)。
- **ESP センサー側の変更は不要**: ESP は `http://192.168.4.1:5000/api/temperature` に
  POST しているので、Pi の LAN 側 IP が変わっても影響なし。
- **ダッシュボード URL**: これまで `http://192.168.11.200:5000/` でブックマークして
  いた場合、以降は `http://takemetothehospital:5000/` (MagicDNS) か
  `http://100.x.x.x:5000/` (Tailscale IP) を使う。

## 8. 検証チェックリスト

- [ ] 事前確認 (§1) で機構 (NetworkManager / dhcpcd) を特定した
- [ ] バックアップを取った
- [ ] `ip -4 addr show wlan0` に `dynamic` の表示が出た
- [ ] wlan1 = 192.168.4.1 が変わっていない
- [ ] Tailscale 経由で `ssh pi@100.x.y.z` で入れる
- [ ] ESP センサーが引き続き Flask にデータを送っている (`/api/sensors` 確認)
- [ ] LCD 表示が正常 (AP/WAN のマークが出ている)
- [ ] (現地展開後) 別のルーターに接続して DHCP 取得できた
