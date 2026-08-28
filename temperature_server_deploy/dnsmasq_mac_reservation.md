# dnsmasq DHCP 予約設定ガイド (canonical 版)

3 層分離アーキテクチャ (2026-07-30 導入) における **ネットワーク層の管理方法**。
新規チップを追加するたびに Pi 側で 1 行追記する運用手順書。

## 背景: なぜ DHCP 予約か

本プロジェクトは **MAC 由来 device_id + DHCP 予約 + nickname** の 3 層分離
アーキテクチャを採用 (詳細は `outputs/docs/デバイス識別設計.md` 参照)。

- **識別**: ESP スケッチが起動時に MAC の下位 3 バイトから `device_id` を自動生成
  (例: MAC=`84:CC:A8:A1:B2:C3` → `ESP-A1B2C3`)
- **IP 割当**: このドキュメントの手順に従い、dnsmasq 側で MAC-IP マッピングを固定
- **表示名**: Flask ダッシュボードの「表示名管理」タブで nickname 割当

ESP 側スケッチは **全チップ共通、書換え不要でコピペ書込み可能**。
per-chip の情報は Pi 側 dnsmasq に一元化される。

## 手順

### Step 1: 新チップの MAC アドレスを取得

3 通り (どれか 1 つ)。

#### 方法 A: Get_MAC_Address.ino で確認 (最推奨)

```
outputs/ESP_MAC_Address_Getter/ESP_MAC_Address_Getter.ino
```
を新チップに書き込み、Arduino IDE のシリアル モニタ (115200 bps) で確認:
```
=== ESP32 MAC Address Getter ===
MAC Address: 84:CC:A8:A1:B2:C3
```

#### 方法 B: 温度センサースケッチのシリアル出力で確認

本番スケッチや LED 版はデフォルトでは Serial.print しないが、デバッグ版
(`ESP8266_DeepSleep_FixedIP_Sensor_debug`) は起動時に MAC を出力する:
```
[BOOT] full_mac=84:CC:A8:A1:B2:C3
[BOOT] device_id=ESP-A1B2C3 (MAC lower 3 bytes)
```

#### 方法 C: Pi の journal で確認 (既に接続済みなら)

チップを一度でも Pi の AP に接続させて:
```bash
sudo journalctl -u dnsmasq --since "10 minutes ago" | grep -i DHCP
```
`DHCPACK(wlan1) 192.168.4.150 84:cc:a8:a1:b2:c3` のような行から MAC を採取。

### Step 2: dnsmasq に予約エントリを追加

Pi の SSH で:

```bash
sudo nano /etc/dnsmasq.d/wlan1.conf
```

末尾に以下の書式で **1 チップ 1 行** 追加:

```
# ===== MAC-IP 予約 (3 層分離アーキテクチャ、2026-07-30 以降 canonical) =====
# 書式: dhcp-host=<MAC>,<予約 IP>,<hostname (任意)>
dhcp-host=84:cc:a8:a1:b2:c3,192.168.4.208,ESP-A1B2C3
dhcp-host=84:cc:a8:d4:e5:f6,192.168.4.209,ESP-D4E5F6
dhcp-host=84:cc:a8:78:9a:bc,192.168.4.210,ESP-789ABC
```

書式の細則:
- MAC は **小文字コロン区切り** で書く (`aa:bb:cc:dd:ee:ff`)
- 予約 IP は AP subnet (192.168.4.0/24) 内で、DHCP プール範囲 (100-199) と
  重ならない範囲を推奨 → **200-254 番** を予約専用領域とする慣例
- hostname は任意。Pi 側 arp テーブルや dhcp lease で見えるだけの識別用

### Step 3: dnsmasq を再起動して反映

```bash
sudo systemctl restart dnsmasq
sudo systemctl status dnsmasq --no-pager
```

`Active: active (running)` になれば OK。設定エラーがあれば journalctl で確認:

```bash
sudo journalctl -u dnsmasq -n 20 --no-pager
```

### Step 4: ESP チップに本番スケッチをコピペ書込み

以下のどれかを **書換え無し** で書き込む:

- `outputs/ESP8266_DeepSleep_FixedIP_Sensor/` (本番)
- `outputs/ESP8266_DeepSleep_FixedIP_Sensor_LED/` (現地診断用)
- `outputs/ESP8266_DeepSleep_FixedIP_Sensor_debug/` (開発時)
- `outputs/ESP32_DS18B20_WiFi/` (ESP32 常時給電)
- `outputs/ESP32_DS18B20_WiFi_Battery/` (ESP32 電池)

これらは全て起動時に MAC から自動で device_id を生成する。

### Step 5: 動作確認

Pi 側で受信確認:

```bash
sudo journalctl -u temperature-server -f
```

期待される見え方:
```
[POST /api/temperature] from 192.168.4.208: {"device_id":"ESP-A1B2C3","name":"ESP-A1B2C3",...}
[POST /api/temperature] ESP-A1B2C3 (ESP-A1B2C3): temp=24.5 saved at ...
```

ブラウザで `http://192.168.11.200:5000/` を開くと、`ESP-A1B2C3` が
ダッシュボードに登場する。

### Step 6: nickname 割当

`http://192.168.11.200:5000/management` → 「🏷️ 表示名管理」タブ → 
新規追加された `ESP-A1B2C3` に「冷却塔1」等の表示名を入力して保存。

以降、ダッシュボードやグラフで nickname 優先表示になる。

## 予約 IP プール設計 (推奨)

wlan1.conf 全体の DHCP プール設定:

```
interface=wlan1
bind-interfaces
domain-needed
bogus-priv
no-resolv
listen-address=192.168.4.1

# DHCP プール範囲 (未予約の動的割当領域)
dhcp-range=192.168.4.100,192.168.4.199,255.255.255.0,24h

# MAC-IP 予約 (200-254 は予約専用領域)
# 新チップ追加時はここに dhcp-host= 行を追加
dhcp-host=84:cc:a8:a1:b2:c3,192.168.4.208,ESP-A1B2C3
dhcp-host=84:cc:a8:d4:e5:f6,192.168.4.209,ESP-D4E5F6
```

- **100-199**: 一時接続 (スマホ、PC 等) 用の動的プール
- **200-254**: ESP デバイスの予約専用領域

## チップ交換手順

センサーが故障して物理的に交換する時:

```
1. 新チップの MAC を取得 (Step 1)
2. dnsmasq.conf の旧 MAC の行をコメントアウト or 削除
3. 新 MAC の行を追加 (旧 IP を引き継ぐ)
   例:
     # dhcp-host=84:cc:a8:a1:b2:c3,192.168.4.208,ESP-A1B2C3  ← 旧 (廃棄)
     dhcp-host=84:cc:a8:99:88:77,192.168.4.208,ESP-998877     ← 新
4. sudo systemctl restart dnsmasq
5. 新チップにスケッチをコピペ書込み
6. ダッシュボードで新 device_id "ESP-998877" が現れる
7. 管理画面で nickname を「冷却塔1」に再割当 (旧の "ESP-A1B2C3" は削除可)
```

**メリット**: IP が同じままなので、物理ラベル (「208 番は冷却塔1」等) を貼り替える
必要なし。運用の連続性が保たれる。

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| dnsmasq が予約通り IP を渡さない | MAC のスペル間違い or 大文字混在 | 小文字コロン区切りに統一、`systemctl restart dnsmasq` |
| dnsmasq がエラーで起動しない | conf の書式ミス | `journalctl -u dnsmasq -n 20` でエラー行確認 |
| 別のクライアントに予約 IP が奪われる | 予約なしの DHCP プールが 200-254 まで広い | プールを 100-199 に狭める (§ 予約 IP プール設計) |
| 予約したのに 192.168.4.100 が振られる | 該当 MAC の dhcp-host エントリが無い or 反映されていない | 設定確認 → dnsmasq 再起動 |

## 補足: なぜ静的 IP (WiFi.config) を使わないか

過去バージョン (2026-07-27 まで) は ESP スケッチ側で `WiFi.config(fixedIP, ...)` に
より静的 IP を宣言していた。しかし:

- チップごとにスケッチを書換える運用負担が大きい
- IP と SENSOR_ID を手動で一致させる必要があり、コピペミスの温床
- 電池省電力効果は誤差レベル (WiFi.config vs DHCP 予約で 1-2%)
- **識別 (device_id) と IP 管理を Pi 側 dnsmasq に一元化する方が運用堅牢**

DHCP 予約は Pi 側 dnsmasq に MAC-IP マッピングを事前登録するので、DHCP 折衝は
1 往復で完了 (通常 3-4 往復) し、実質的には静的 IP と同等の速度で IP が確定する。

## 関連ドキュメント

- `outputs/docs/デバイス識別設計.md` — 3 層分離アーキテクチャの設計思想
- `outputs/docs/Arduino_IDE_設定ガイド.md` — ESP チップへの書込み手順
- `outputs/docs/RaspberryPi_セットアップガイド.md` — Pi 全体構築
- `outputs/ESP_MAC_Address_Getter/` — MAC 取得ユーティリティ
