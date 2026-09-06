# TP-Link Archer T2U Plus 非公式ドライバー導入ガイド (Raspberry Pi 用)

## はじめに

TP-Link Archer T2U Plus は AC600 USB 無線 LAN アダプタで、Raspberry Pi に **2つ目の Wi-Fi インターフェース (`wlan1`)** を増やす用途でよく使われます。本ガイドでは、これを Raspberry Pi OS Bookworm / Trixie 上で動かし、**AP モード (アクセスポイント) として使える状態まで持っていく**手順を、実機で確認した内容に基づいてまとめます。

メーカー公式の Linux ドライバーは Raspberry Pi OS のサポートが薄く、最新カーネルでは動かないため、GitHub で広く使われている **morrownr 氏の有志ドライバー** を導入します。

> **本ガイドの最重要ポイント:** Archer T2U Plus は **搭載チップが RTL8821AU** なので、morrownr 氏の **`8821au-20210708`** リポジトリを使う必要があります。似た名前の **`8812au-20210820`** (RTL8812AU 用) を選ぶと、Archer T2U Plus は **`wlan1` が作成された状態でも AP モード起動時に `Operation not permitted` エラーが出続けて詰みます** (実機検証済みの罠)。§1 のチップ→リポジトリ対応表を必ず確認してください。

---

## 0. 動作確認済み環境

| 項目 | 値 |
|---|---|
| 機種 | Raspberry Pi 4 Model B |
| OS | Raspberry Pi OS (Trixie / Debian 13) 64bit |
| カーネル | 6.12.75+rpt-rpi-v8 |
| USB ドングル | TP-Link Archer T2U Plus (USB ID `2357:0120`、チップ `RTL8821AU`) |
| 用途 | AP モード (hostapd + dnsmasq で利用) |
| ドライバー | **morrownr/8821au-20210708** (v5.12.5.2、USB ID 追記不要) |

Pi 3B+ / Pi 5 / Bookworm でも同じ手順で動作します (パッケージ名の差は §2 の表で吸収)。

### 実証済みの動作範囲

本ガイドの手順を新規 SD カード (Trixie 64bit) で通し実行し、以下まで確認済み:

- DKMS 経由でのドライバービルド → `rtl8821au/5.12.5.2, 6.12.75+rpt-rpi-v8, aarch64: installed`
- `wlan1` が Realtek OUI の MAC で作成、`driver` シンボリックリンクが `rtl8821au` を指す
- `iw phy phy1 info` で `Supported interface modes: * AP` が宣言される
- `hostapd` (SSID `YOUR_AP_SSID_HERE` / passphrase `YOUR_AP_PASSWORD_HERE` / channel 6) で `AP-ENABLED` に到達
- `dnsmasq` (当時の検証構成: dhcp-range 192.168.4.2-254) と組み合わせて **スマホから接続 + DHCP 取得** に成功
  ※ 本番構成のアドレス設計は `.228-.254` プール。§9-5 と `docs/デバイス識別設計.md` を参照

---

## 1. デバイス情報の確認

USB ドングルを Pi に挿してから:

```bash
lsusb
```

例:

```
Bus 001 Device 004: ID 2357:0120 TP-Link Archer T2U PLUS [RTL8821AU]
```

| 列 | 意味 |
|---|---|
| `2357` | ベンダーID (VID)。TP-Link 共通 |
| `0120` | プロダクトID (PID)。**製品リビジョンで変わる** |
| `RTL8821AU` | 搭載チップ。どのリポジトリを使うか決まる |

### チップごとのドライバーリポジトリ

| 搭載チップ | 使うリポジトリ | 備考 |
|---|---|---|
| **RTL8811AU / RTL8821AU** ← Archer T2U Plus はこれ | **https://github.com/morrownr/8821au-20210708** | v5.12.5.2、AP モード実績豊富 |
| RTL8812AU | https://github.com/morrownr/8812au-20210820 | **RTL8821AU には使わない**。alias に PID があっても実運用で EPERM が出る |
| RTL8812BU / RTL8822BU | https://github.com/morrownr/88x2bu-20210702 | -- |
| RTL8811CU / RTL8821CU | https://github.com/morrownr/8821cu-20210916 | -- |

**本ガイドは Archer T2U Plus (RTL8821AU) 前提で `8821au-20210708` で進めます。** 他のチップでも、リポジトリ名が違うだけで手順は同じです。

> **なぜ 8812au-20210820 を選んではいけないか:** 一見 RTL8821AU にも対応しているように見えます (README に「8811AU/8821AU も対応」とあった時期がある)。しかし実機で試すと `hostapd` 起動時に `nl80211: Could not configure driver mode` と共に `Operation not permitted` エラーが出て AP モードが動きません。ドライバー内部の初期化パスが RTL8812AU 向けに書かれているためで、`ip link set wlan1 up` 単発でも同じエラーになります。この罠に 3 日以上費やす人が多いので、**チップ名 (RTL8821AU) とリポジトリ名 (8821au) の一致** を最初に確認するのが最も確実な避け方です。

---

## 2. 事前準備 (ビルドツール・カーネルヘッダ)

### OS / アーキ / カーネルを確認

```bash
cat /etc/os-release | grep VERSION_CODENAME
# bookworm / trixie / bullseye

uname -r
# 例: 6.12.75+rpt-rpi-v8

uname -m
# aarch64 (64bit) / armv7l (32bit)
```

### カーネルヘッダパッケージ対応表

カーネルヘッダは **OS バージョン × Pi モデル/アーキ** で名前が変わります。

| OS | Pi モデル/アーキ | ヘッダパッケージ名 |
|---|---|---|
| Bookworm | Pi 3/4 (aarch64) | `linux-headers-$(uname -r)` または `raspberrypi-kernel-headers` |
| Bookworm | 32bit (armv7l) | `linux-headers-$(uname -r)` または `raspberrypi-kernel-headers` |
| **Trixie** | Pi 3/4 (aarch64) | `linux-headers-rpi-v8` |
| **Trixie** | Pi 5 (aarch64) | `linux-headers-rpi-2712` |
| **Trixie** | 32bit (armv7l) | `linux-headers-rpi-v7l` |
| Bullseye | aarch64 | `linux-headers-$(uname -r)` または `raspberrypi-kernel-headers` |

> **重要 (Trixie 以降):** `raspberrypi-kernel-headers` パッケージは **Bookworm までで廃止**されています。Trixie で `sudo apt install raspberrypi-kernel-headers` を実行すると `Error: Unable to locate package` で止まります。

### インストール (Trixie / Bookworm 両対応)

`apt install` はパッケージが 1 つでも見つからないと全体を中止するので、**ビルドツールとヘッダを分けて入れる**のが安全です:

```bash
sudo apt update

# (1) ビルドツール (ヘッダ以外)
sudo apt install -y git build-essential bc dkms

# (2) ヘッダ (一般指定 → 明示パッケージ名へフォールバック)
sudo apt install -y linux-headers-$(uname -r) || \
sudo apt install -y linux-headers-rpi-v8 || \
sudo apt install -y linux-headers-rpi-2712 || \
sudo apt install -y linux-headers-rpi-v7l || \
sudo apt install -y raspberrypi-kernel-headers
```

### 確認

```bash
dpkg -l | grep -E 'linux-headers|^ii  dkms|^ii  build-essential|^ii  git'
# それぞれ "ii" (installed) で出ていれば OK
```

---

## 3. ドライバーソースの取得

morrownr 氏の README 推奨に従い `~/src/` 配下に配置します:

```bash
mkdir -p ~/src
cd ~/src
git clone https://github.com/morrownr/8821au-20210708.git
cd 8821au-20210708

# clone された内容を確認
ls
```

期待する主要ファイル/ディレクトリ:

- `install-driver.sh` `remove-driver.sh` (導入・削除スクリプト)
- `dkms.conf` `Makefile` (ビルド設定)
- `README.md` `FAQ.md` `supported-device-IDs` (ドキュメント)
- `core/` `hal/` `os_dep/` `include/` `platform/` (ソースツリー)

(RTL8812BU 系を使う場合は `git clone https://github.com/morrownr/88x2bu-20210702.git` に読み替え)

---

## 4. USB ID 対応の確認 (通常は追記不要)

正しいリポジトリ (`8821au-20210708`) を選んでいる場合、**Archer T2U Plus (PID `0x0120`) は最初からサポート ID 表に登録済み** なのでソース追記は不要です。念のため実測で確認します:

### 4-1. `supported-device-IDs` 一覧を確認

```bash
cd ~/src/8821au-20210708

echo "=== TP-Link 系対応 ID ==="
grep -iE '2357|TP-Link|Archer T2U' supported-device-IDs
```

期待する出力 (`8821au-20210708` の現行コミット):

```
ID 2357:011e /* TP Link */
ID 2357:011f /* TP Link */
ID 2357:0120 /* TP Link */    ← Archer T2U Plus
```

### 4-2. ソースコードの USB ID テーブルを直接確認

```bash
grep -n "0x2357" os_dep/linux/usb_intf.c
```

期待する出力抜粋:

```
181:    {USB_DEVICE(0x2357, 0x0101), .driver_info = RTL8812}, /* TP-Link - Archer T4U AC1200 */
182:    {USB_DEVICE(0x2357, 0x0103), .driver_info = RTL8812}, /* TP-Link - T4UH */
183:    {USB_DEVICE(0x2357, 0x010D), .driver_info = RTL8812}, /* TP-Link - Archer T4U AC1300 */
184:    {USB_DEVICE(0x2357, 0x010E), .driver_info = RTL8812}, /* TP-Link - Archer T4UH AC1300 */
185:    {USB_DEVICE(0x2357, 0x010F), .driver_info = RTL8812}, /* TP-Link - T4UHP */
214:    {USB_DEVICE(0x2357, 0x011E), .driver_info = RTL8821}, /* TP Link */
215:    {USB_DEVICE(0x2357, 0x011F), .driver_info = RTL8821}, /* TP-Link */
216:    {USB_DEVICE(0x2357, 0x0120), .driver_info = RTL8821}, /* TP Link */   ← Archer T2U Plus
```

**判定の要点**:

- `0x0120` が **`.driver_info = RTL8821`** として登録されている = チップ種別も正しく分類されている
- 8812au-20210820 リポジトリでは `0x0120` は未登録 (要手動追記) だったのに対し、**8821au-20210708 では追記不要**

### 4-3. §1 の `lsusb` で見た自分の PID と照合

- 自分の PID が **RTL8821 セクションに含まれている** (`0x011E`, `0x011F`, `0x0120` など) → §6 (ビルド + インストール) へ進む
- 自分の PID が **RTL8812 セクションに含まれている** (`0x0101`, `0x0103` など) → 本来は別リポジトリ (`8812au-20210820`) を使うべき。もし本ガイドの `8821au-20210708` でそのまま進める場合、動く場合もあるが AP モードで詰まる可能性がある
- 自分の PID が **どちらにもない** → 付録 A (別チップ製品で対応 PID を追記する非常手段) を参照

---

## 6. ビルド + DKMS インストール

DKMS を使うと、カーネル更新時にもドライバが**自動再ビルド**されるため、長期運用に有利です。ログを残しながら実行:

```bash
cd ~/src/8821au-20210708
sudo ./install-driver.sh 2>&1 | tee ~/install-driver.log
```

> **注意 (リポジトリ仕様変更):** 古い morrownr リポジトリには `raspi64.sh` / `raspi32.sh` という Raspberry Pi 用事前設定スクリプトがありましたが、**現行版では廃止**されています。`install-driver.sh` が内部で `uname -m` を読んでアーキを自動判定するようになりました。直接 `install-driver.sh` を叩いてください (古いブログ記事の手順を踏襲して `./raspi64.sh: No such file or directory` で詰まる人が後を絶ちません)。

### 対話プロンプト

`install-driver.sh` はリポジトリのバージョンによって対話プロンプトの構成が違います。下記の **いずれか** が表示されるはずです。

#### パターン A: 古めのコミット (reboot 要求あり)

| 質問 | 回答 |
|---|---|
| `Do you want to edit the driver options file?` | `n` |
| `Do you want to apply the new driver options now?` | `n` |
| **`Do you want to reboot now?`** | **`y` (必須)** |

#### パターン B: 最新コミット (reboot 要求なし — 2026年時点で確認)

| 質問 | 回答 |
|---|---|
| `Do you want to edit the driver options file?` | `n` |
| `Do you want to apply the new driver options now?` | `n` |
| (reboot プロンプトは無く、そのままシェルに戻る) | スクリプト完走後に **手動で `sudo reboot`** |

> **重要:** どちらのパターンでも、**ドライバーがカーネルにロードされるにはリブートが必要**です。パターン B のときは、スクリプト完走後に必ず手動でリブートしてください:
>
> ```bash
> sudo reboot
> ```

### スクリプト完走の確認方法

リブート前に DKMS への登録が成功しているかを念のため確認:

```bash
sudo dkms status
# rtl8821au/5.12.5.2, 6.12.75+rpt-rpi-v8, aarch64: installed   ← この行が出ていれば成功

# プロンプト構成を実物で見たい場合
tail -30 ~/install-driver.log
```

---

## 7. リブート後のインターフェース命名確認

リブート完了後、まず **`wlan0` / `wlan1` がどのデバイスに割り当てられたか** を確認します。

```bash
ip link
```

期待する並び (実証済み):

```
3: wlan0: ... link/ether e4:5f:01:XX:XX:XX  ← オンボード Broadcom (Raspberry Pi Trading の OUI)
4: wlan1: ... link/ether cc:ba:bd:XX:XX:XX  ← Archer T2U Plus (Realtek の OUI)
```

| MAC OUI | 製造元 | 期待される割当 |
|---|---|---|
| `e4:5f:01:...` | Raspberry Pi Trading | `wlan0` (オンボード Wi-Fi = インターネット側) |
| `cc:ba:bd:...` / `00:e0:4c:...` / `00:0e:8e:...` 等の Realtek OUI | Realtek | `wlan1` (USB ドングル = AP 側) |

**実証環境 (Trixie kernel 6.12.75 + morrownr/8821au-20210708)** では、追加の設定なしで期待通りの並びで起動しました。命名スワップは発生していません。

### ケースA: 期待通りに並んでいる → §8 へ進む

`wlan0` = オンボード、`wlan1` = Archer T2U Plus になっていれば追加設定は不要。§8 (インストール確認) に進んでください。**このケースが実証環境で確認された標準パターン**です。

### 参考: ケースB (万一 wlan0/wlan1 が入れ替わっている場合)

もし `wlan0` が Realtek、`wlan1` が Broadcom になっている場合 (= USB ドライバが Broadcom より先に NIC 登録された結果)、後続の AP セットアップガイドの記述と整合しません。MAC アドレスをキーに名前を固定します:

```bash
# 自分の環境の MAC を確認 (上の ip link の出力から控えておく)
ONBOARD_MAC=$(ip link show | awk '/link\/ether/ && /e4:5f:01/ {print $2; exit}')
USB_MAC=$(ip link show | awk '/link\/ether/ && !/e4:5f:01/ && !/00:00:00/ {print $2; exit}')

echo "Onboard (Broadcom): $ONBOARD_MAC -> wlan0"
echo "USB (Realtek):      $USB_MAC -> wlan1"

# udev rule で固定
sudo tee /etc/udev/rules.d/70-persistent-net.rules <<EOF
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$ONBOARD_MAC", NAME="wlan0"
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$USB_MAC", NAME="wlan1"
EOF

sudo udevadm control --reload-rules
sudo reboot
```

リブート後にもう一度 `ip link` で並びを確認。期待通りになっていれば §8 へ。

> **`/etc/modules-load.d/8821au.conf` を作るかどうかの判断:** 実証環境ではこのファイルを作らずに DKMS 経由で自動ロードされました (リブート後 `lsmod` に `8821au` が出て `wlan1` が正しく作成)。過去には USB ドライバの起動時早期ロードが命名スワップを引き起こす副作用が確認されていたため、**必要性が確認できない限り作らない** のが安全です。もし DKMS 直後の初回起動で `wlan1` が出ない場合は、まず `sudo modprobe 8821au` で手動ロードを試し、それで動くなら自動ロード設定は不要です。

---

## 8. インストール確認

リブート完了後、次の 5 つすべてが期待値になることを確認します。**判定の決定的証拠は (4) と (5)** です。ドライバが USB デバイスに正しくアタッチされていれば、`wlan1` インターフェースが Realtek OUI の MAC で作られ、`driver` シンボリックリンクが `rtl8821au` を指します。

```bash
# (1) DKMS への登録状態
sudo dkms status
# rtl8821au/5.12.5.2, 6.12.75+rpt-rpi-v8, aarch64: installed
```

```bash
# (2) モジュールがロード済みか
lsmod | grep 8821au
# 8821au               2260992  0
# cfg80211             1052672  2 8821au,brcmfmac
#
# ※ 8821au の末尾の数字 (Used by 列) は 0 のままが正常です。
#   これは「8821au に依存する他モジュールが無い」という意味で、
#   USB デバイスへのアタッチ状態を示す指標ではありません。
#   実際のアタッチ確認は下の (4) と (5) で行います。
```

```bash
# (3) 対応 USB ID 表に自分のデバイスが含まれているか
modinfo 8821au | grep -i "v2357p0120"
# usb:v2357p0120d*dc*dsc*dp*ic*isc*ip*in*
```

```bash
# (4) wlan1 が Realtek の MAC アドレスで作られているか (アタッチ完了の証拠)
ip link
# 4: wlan1: <NO-CARRIER,BROADCAST,MULTICAST,UP,LOWER_UP> ...
#     link/ether cc:ba:bd:XX:XX:XX ...    ← Realtek OUI (cc:ba:bd, 00:e0:4c 等)
```

```bash
# (5) 【決定的証拠】 driver シンボリックリンクが rtl8821au を指すか
readlink /sys/class/net/wlan1/device/driver
# ../../../../../../../../../../../bus/usb/drivers/rtl8821au
```

**判定の要点**:

- (5) で末尾が **`rtl8821au`** なら、正しいドライバがデバイスに bind されている
- もし末尾が `rtl8812au` になっていたら、**間違ったリポジトリを入れている** = §13 のトラブル項目「`Operation not permitted` (hostapd 起動時)」に該当する状態

念のため `iw dev` でも確認:

```bash
# (6) 補助確認: phy と interface の対応
iw dev
# phy#1
#     Interface wlan1
#         addr cc:ba:bd:XX:XX:XX
#         type managed       ← まだ AP モードにしていないので managed
# phy#0
#     Interface wlan0
#         addr e4:5f:01:XX:XX:XX
#         ssid YOUR_HOME_WIFI_SSID  (自宅または現場のルーター)
#         type managed
```

すべて期待値なら成功です。§9 で AP モード動作を単体テストするか、AP セットアップガイド (Raspberry Pi DHCPAPセットアップガイド.md) に進みます。

---

## 9. AP モードのテスト (単体動作確認)

ドライバが AP モードで動くことを、hostapd を **前面実行 (foreground)** で単体テストします。**永続化はまだ行いません** (それは AP セットアップガイド側)。

### 9-1. AP モードのサポート宣言を確認

先に `iw phy phy1 info` で phy1 (Realtek 8821au) が `* AP` を宣言していることを確認します。ドライバの内部整合性のチェックです:

```bash
sudo iw phy phy1 info | grep -A 15 "Supported interface modes"
```

期待:

```
Supported interface modes:
    * IBSS
    * managed
    * AP         ← ここが決定的
    * monitor
    * P2P-client
    * P2P-GO
```

### 9-2. NetworkManager から wlan1 を unmanaged にする (ランタイム、一時的)

hostapd が wlan1 を排他的に扱えるように、NetworkManager から解放します。**恒久設定ではなく実行時の一時設定**なので、リブートで元に戻ります (永続化は AP セットアップガイドで扱う):

```bash
sudo nmcli device set wlan1 managed no
nmcli device status | grep wlan1
# wlan1  wifi  unmanaged  --
```

### 9-3. wlan1 に静的 IP を割り当て、hostapd を起動

```bash
sudo apt install -y hostapd

sudo ip addr add 192.168.4.1/24 dev wlan1
sudo ip link set wlan1 up

cat << 'EOF' | sudo tee /tmp/hostapd-test.conf
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

sudo hostapd /tmp/hostapd-test.conf
```

### 9-4. 期待するログと成功マーカー

```
Configuration file: /tmp/hostapd-test.conf
Using interface wlan1 with hwaddr cc:ba:bd:XX:XX:XX and ssid "YOUR_AP_SSID_HERE"
wlan1: interface state UNINITIALIZED->COUNTRY_UPDATE
wlan1: interface state COUNTRY_UPDATE->ENABLED
wlan1: AP-ENABLED                                    ← ★ 成功マーカー
```

`AP-ENABLED` が表示されたら、スマホの Wi-Fi 一覧に **`YOUR_AP_SSID_HERE`** が現れることを確認してください。

停止は `Ctrl+C`。

### 9-5. DHCP まで通したい場合 (完全な接続テスト)

hostapd だけではスマホに IP が配られません。dnsmasq を追加設定してから接続テストする場合の最小手順:

```bash
sudo apt install -y dnsmasq

sudo tee /etc/dnsmasq.d/wlan1.conf > /dev/null << 'EOF'
interface=wlan1
# ESP は .100-.227 を自分で静的宣言する (方式D)。プールはそこと重ねない
dhcp-range=192.168.4.228,192.168.4.254,255.255.255.0,24h
dhcp-option=option:router,192.168.4.1
dhcp-option=option:dns-server,8.8.8.8,8.8.4.4
EOF

sudo systemctl restart dnsmasq
```

この状態で hostapd を起動し、スマホから `YOUR_AP_SSID_HERE` に接続 (パスフレーズ `YOUR_AP_PASSWORD_HERE`) すると:

- hostapd 側に `AP-STA-CONNECTED <スマホMAC>` が出る
- dnsmasq 側に `DHCPACK(wlan1) 192.168.4.X <スマホMAC>` が出る
- スマホに 192.168.4.X の IP が付与される (**実証済み**)

### 9-6. 恒久運用への移行

Ctrl+C で hostapd を停止したら、この時点で組んだ一時設定 (unmanaged、静的 IP、dnsmasq config) はリブートで揮発します (unmanaged と静的 IP は。dnsmasq config はファイルなので残る)。

恒久的に AP として運用するには、これらを systemd unit と永続的な NetworkManager 設定に落とし込みます。詳細は別ガイド「Raspberry Pi DHCPAPセットアップガイド.md」参照。

---

## 10. ドライバー削除 (アンインストール)

DKMS 経由で入れているので:

```bash
cd ~/src/8821au-20210708
sudo ./remove-driver.sh
```

または:

```bash
sudo dkms remove rtl8821au/5.12.5.2 --all
```

(バージョン番号は `sudo dkms status` で確認した値に置き換え)

---

## 11. カーネル更新時の自動追従

DKMS で入っていれば、`apt upgrade` でカーネルが上がっても次回起動前に自動再ビルドされます:

```bash
sudo dkms status
# rtl8821au/5.12.5.2, NEW-KERNEL-VERSION, aarch64: installed
```

`installed` 表記なら新カーネルでも動く状態。`built` で止まっていれば手動で:

```bash
sudo dkms autoinstall
```

---

## 12. 周波数 (5GHz) の制限について

Archer T2U Plus は AC600 規格で **5GHz も使える**チップですが、AP として 5GHz を使う場合の制約:

- `country_code=JP` 必須
- DFS (動的周波数選択) チャンネルは AP 用途で非対応のことが多い → **W56 (100ch〜) を避ける**
- 使えるのは概ね **W52 (36/40/44/48ch)** のみ

ESP-WROOM-02 / ESP8266 系は **2.4GHz のみ対応** なので、本シリーズでは 5GHz を使う必要はなく、`hw_mode=g` `channel=6` で十分です。

---

## 13. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| **`Operation not permitted` が `hostapd` 起動時や `ip link set wlan1 up` で出る** (本ガイド最大の落とし穴) | **チップと違うリポジトリ (`8812au-20210820`) を導入している**。RTL8821AU 用に RTL8812AU 用ドライバを当てるとこの症状で 3 日ハマる | 導入済みドライバを完全撤去する: `sudo ./remove-driver.sh` (誤リポジトリのソースディレクトリで実行) → `sudo dkms remove rtl8812au/x.x.x --all` → ソースディレクトリを `rm -rf`。その上で本ガイドの §3 から (`morrownr/8821au-20210708`) で入れ直す。§8 (5) の `readlink /sys/class/net/wlan1/device/driver` で `rtl8821au` が返ることを確認 |
| `Error: Unable to locate package raspberrypi-kernel-headers` | OS が **Trixie** 以降。当該パッケージは Bookworm までで廃止 | §2 の表を参照し、`linux-headers-rpi-v8` (aarch64) や `linux-headers-rpi-2712` (Pi 5) を入れる |
| `bash: ./raspi64.sh: No such file or directory` | morrownr リポジトリ最新版で事前設定スクリプトが廃止された | `install-driver.sh` を直接実行する (内部でアーキ自動判定) |
| `install-driver.sh` 完走後に `reboot now?` プロンプトが出ない | 最新コミットでは reboot 確認が省略されている | 手動で `sudo reboot` を実行。DKMS への登録は完了済み (`sudo dkms status` で `installed` を確認) |
| `Errors were encountered while processing` (apt) | ヘッダパッケージが旧バージョン | `sudo apt full-upgrade` 後にカーネルヘッダ再導入 |
| リブートしても `lsmod` に `8821au` が出ない | DKMS インストール直後で自動ロードがまだ走っていない | まず `sudo modprobe 8821au` で手動ロードを試す。それで動くなら `/etc/modules-load.d/8821au.conf` は作らない (命名スワップの副作用回避のため。§7 の注記参照) |
| リブート後 `wlan0` が Realtek、`wlan1` が Broadcom と入れ替わっている | USB ドライバがオンボード Wi-Fi (brcmfmac) より先にロードされ、NIC 登録が逆順になった | §7 ケース B の MAC ベース udev rule で固定 |
| `lsmod` には出るが `ip link` に `wlan1` が出ない | USB 認識失敗 or ドライバとデバイスの ID マッチ失敗 | `lsusb` で USB デバイスが認識されていることを確認。`modinfo 8821au \| grep v2357p0120` で PID がドライバ alias にあることを確認。無ければ付録 A 参照 |
| `error: implicit declaration of function ...` (ビルド時) | ソースが新カーネルに未対応 | `git pull` で最新化。それでもダメなら kernel 6.14 以降なら in-kernel の `rtw88` ドライバ検討 (README 冒頭のNotice参照) |
| `wlan1` 認識するが Wi-Fi スキャンできない | nl80211 と未統合 | `sudo modprobe -r 8821au && sudo modprobe 8821au` で再ロード |
| AP は立つがクライアントが繋がらない | `country_code` 未設定 or WPA passphrase 不整合 | `country_code=JP` を hostapd.conf に追加。passphrase を再確認 |
| 突然 `wlan1` が消える | USB 電源不足 | セルフパワー USB ハブ経由で給電 |
| カーネル更新後に動かない | DKMS 再ビルド失敗 | `sudo dkms autoinstall` で手動再ビルド |
| `Operation not supported (-95)` (hostapd) | チップが AP モード非対応 or 別ドライバが掴んでいる | `readlink /sys/class/net/wlan1/device/driver` が `rtl8821au` を指すか確認。§14 の `iw list` で `AP` 対応か確認 |

---

## 14. `iw list` での AP モード対応確認

ドライバー導入後、AP モードで使えるかを事前に確認できます:

```bash
sudo iw list | grep -A 12 "Supported interface modes"
```

期待する出力:

```
Supported interface modes:
    * IBSS
    * managed
    * AP                ← この行があれば AP 利用可
    * AP/VLAN
    * monitor
    * mesh point
    * P2P-client
    * P2P-GO
```

`AP` の行がなければ別リポジトリへ乗り換える必要があります。

---

## 15. 関連ドキュメント

- 「Raspberry Pi DHCPAPセットアップガイド.md」 — wlan1 を AP として運用する hostapd/dnsmasq 構築
- 「電池駆動配線ガイド.md」 — ESP 側のハード
- 「ESP8266_DS18B20_HTTPPOST.ino のブログ解説.md」 — ESP 側のソフト

---

## 付録 A: 別チップ製品で PID 未対応だった場合の追記手順 (非常手段)

**通常は不要です**。本ガイド (RTL8821AU + Archer T2U Plus) の範囲では 8821au-20210708 の対応 ID 表に `0x0120` が最初から含まれるため、この付録は使いません。

別チップ製品で `modinfo 8821au | grep <自分のPID>` が空になる場合の追記手順:

```bash
cd ~/src/8821au-20210708

# 既存の 0x0120 行を参考にして、自分の PID を追加
sudo sed -i '/0x2357, 0x0120.*RTL8821/a\    {USB_DEVICE(0x2357, 0xYOUR_PID), .driver_info = RTL8821}, /* Your Device */' os_dep/linux/usb_intf.c

# 追加確認
grep -n "0x2357" os_dep/linux/usb_intf.c

# 再ビルド + 再インストール
sudo ./remove-driver.sh
sudo ./install-driver.sh
sudo reboot
```

sed のタブ処理で問題が出る場合は `nano os_dep/linux/usb_intf.c` で手動編集し、既存 `0x0120` 行の下に同書式で追加。

---

## 付録 B: 主要な有志ドライバーリポジトリ

| チップ | 主要リポジトリ | 備考 |
|---|---|---|
| **RTL8811AU / RTL8821AU** | **https://github.com/morrownr/8821au-20210708** | v5.12.5.2、本ガイドの主軸 |
| RTL8812AU | https://github.com/morrownr/8812au-20210820 | RTL8821AU には非推奨 (§1 参照) |
| RTL8812BU / RTL8822BU | https://github.com/morrownr/88x2bu-20210702 | -- |
| RTL8811CU / RTL8821CU | https://github.com/morrownr/8821cu-20210916 | -- |
| RTL8814AU | https://github.com/morrownr/8814au | -- |

morrownr 氏は複数のドライバーを並行メンテナンスしているので、別チップに乗り換える時もこの方の他リポジトリから探すと連続性が保てます。

なお 8821au-20210708 の README 冒頭に **「kernel 6.14 以降なら in-kernel の rtw88 ドライバーで動く」** との案内があります (`lwfinger/rtw88` を紹介)。将来 kernel が上がったら乗り換えを検討する余地があります。

---

## まとめ — 同じ罠にハマらないための要点

ブログ/note で本ガイドを公開する際は、特に下記 6 点を押さえると読者の詰まりが激減します:

1. **【最重要】チップ名 (RTL8821AU) とリポジトリ名 (8821au) の一致を確認**
   Archer T2U Plus は RTL8821AU なので `morrownr/8821au-20210708` を使う。似た名前の `8812au-20210820` (RTL8812AU 用) を選ぶと、`hostapd` 起動時に `Operation not permitted` で詰む。本ガイドが解決する最大の罠

2. **OS バージョンでヘッダパッケージ名が違う**
   Trixie で `raspberrypi-kernel-headers` は使えない (`Error: Unable to locate package`)。`linux-headers-rpi-v8` 等を使う

3. **`raspi64.sh` / `raspi32.sh` は廃止された**
   現行 morrownr リポジトリは `install-driver.sh` がアーキ自動判定

4. **インストール完走後は必ずリブートが必要**
   バージョンによって `reboot now?` プロンプトが出る (=`y` を選ぶ) か、何も聞かれずシェルに戻る (=手動で `sudo reboot` を実行する) かが違う。どちらの場合もリブートを忘れると DKMS は installed のままモジュール未ロード

5. **リブート後は `readlink /sys/class/net/wlan1/device/driver` でドライバを確認**
   末尾が `rtl8821au` になっていれば正しく bind されている。`rtl8812au` になっていたら間違ったリポジトリを入れているので撤去してやり直し。`lsmod` の Used by 列 (末尾の数字) は 0 が正常でアタッチ状態を示さない、あくまで `wlan1` の存在 + driver シンボリックリンクで判定

6. **wlan0/wlan1 の命名スワップ対策として `modules-load.d/8821au.conf` は原則作らない**
   DKMS 経由で自動ロードされる (Trixie kernel 6.12.75 で実証)。万一 wlan1 が命名スワップした場合は §7 ケース B の MAC ベース udev rule で対処

これらを順に通せば、Trixie + kernel 6.12 + Pi 4 + Archer T2U Plus (PID `0x0120`) で AP モードまで確実に動作します (実証済み)。
