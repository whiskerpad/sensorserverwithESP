# I2C 20×4 キャラクター LCD 接続・診断・本番導入 統合ガイド

Raspberry Pi 4B に I2C 20×4 キャラクター LCD (HD44780 系、PCF8574 バックパック) を
取り付けて、温度モニタリングシステムの主要ステータス + 各センサーの瞬時温度を
本体で確認できるようにする実施手順書。

**対応時間の目安**:
- 配線: **5 分** (ジャンパー線 4 本のみ、Nokia より遥かに簡単)
- I2C 有効化: **3 分**
- 診断: **5 分**
- 本番導入: **10 分**
- **合計 25 分程度**

---

## 目次

1. [必要な材料](#1-必要な材料)
2. [事前準備](#2-事前準備)
3. [Pi 側 I2C 有効化](#3-pi-側-i2c-有効化)
4. [物理配線](#4-物理配線)
5. [Phase A: 診断スクリプトで表示確認](#5-phase-a-診断スクリプトで表示確認)
6. [Phase B: 本番サービス導入](#6-phase-b-本番サービス導入)
7. [表示レイアウトと運用中の調整](#7-表示レイアウトと運用中の調整)
8. [トラブルシューティング](#8-トラブルシューティング)
9. [Nokia 5110 からの移行 (該当者向け)](#9-nokia-5110-からの移行-該当者向け)
10. [完全撤去手順](#10-完全撤去手順)

---

## 1. 必要な材料

| 項目 | 個数 | 備考 |
|---|---|---|
| I2C バックパック付き 20×4 キャラクター LCD | 1 | PCF8574 バックパック搭載 (「I2C 20x4 LCD」で検索) |
| ジャンパー線 (メス-メス、10-15cm) | 4 本 | Nokia は 8 本必要だったが I2C は 4 本のみ |
| Raspberry Pi 4B | 1 | 稼働中の Pi でよい |

**LCD の見分け方**:
- 大きさ: 約 98×60mm (20×4 は 16×2 より大きい)
- 裏面に **緑 or 青の小さな基板** がハンダ付けされていれば I2C バックパック付き
- バックパック上に **青いトリマ (可変抵抗)** と **ジャンパピン** がある
- 電源は 5V 品が標準 (3.3V 品もあるので実物ラベル確認)

秋月電子・aitendo 等で 1000-1500 円程度。

---

## 2. 事前準備

### 2.1 (Nokia 使用者のみ) Nokia を Pi から削除

Nokia 5110 を先に導入していた場合、競合を避けるため削除:

```bash
sudo systemctl stop nokia-display
sudo systemctl disable nokia-display
sudo rm /etc/systemd/system/nokia-display.service
sudo rm -rf /etc/systemd/system/nokia-display.service.d/
sudo systemctl daemon-reload
rm -rf ~/nokia5110_display
```

Z: 内の `outputs/nokia5110_display/` はそのまま残す (記録・別ハード再利用のため)。

### 2.2 Pi のシャットダウン (物理配線の前)

```bash
sudo shutdown -h now
```

LED (緑) が完全に消灯するまで待ってから電源アダプタを抜く。

---

## 3. Pi 側 I2C 有効化

Nokia の SPI と違い、こちらは **I2C** を有効化します。

### 3.1 raspi-config で有効化

Pi の電源を入れて SSH ログイン:

```bash
sudo raspi-config
```

メニューで:
1. `3 Interface Options`
2. `I5 I2C` (Nokia の場合は I4 SPI だったが、こちらは **I5 I2C**)
3. `Yes` (Enable I2C)
4. `Ok`
5. `Finish` → 再起動

### 3.2 有効化確認

再起動後 SSH 再接続 → 以下:

```bash
ls /dev/i2c-*
```

期待:
```
/dev/i2c-1
```

`/dev/i2c-1` が見えれば OK。

```bash
lsmod | grep i2c
```

`i2c_bcm2835` と `i2c_dev` が表示されれば OK。

### 3.3 i2c-tools インストール

I2C デバイスをスキャンするツール:
```bash
sudo apt install -y i2c-tools
```

### 3.4 pi ユーザーを i2c グループに追加 (通常は自動で入っている)

```bash
groups pi | grep -o i2c
```

`i2c` が表示されなければ:
```bash
sudo usermod -a -G i2c pi
```

**追加後は再ログイン必須** (SSH 抜けて入り直し)。

---

## 4. 物理配線

### 4.1 Pi のシャットダウン

```bash
sudo shutdown -h now
```

LED 消灯 → 電源アダプタを抜く。

### 4.2 配線対応表 (I2C は 4 本のみ!)

| LCD バックパック端子 | Pi Pin | Pi GPIO | 用途 |
|---|---|---|---|
| **GND** | Pin 6 | GND | グラウンド |
| **VCC** | Pin 2 (5V) | - | 電源 (5V) ※ 3.3V 品なら Pin 1 |
| **SDA** | Pin 3 | GPIO2 | I2C データ |
| **SCL** | Pin 5 | GPIO3 | I2C クロック |

**Pi のピン位置** (Pi のロゴを上、USB を右にした向き):
```
Pin 1 (3.3V)   ● ●   Pin 2 (5V)   ★VCC
Pin 3 (GPIO2)  ● ●   Pin 4 (5V)   ★SDA (Pin 3)
Pin 5 (GPIO3)  ● ●   Pin 6 (GND)  ★SCL (Pin 5) と ★GND (Pin 6)
```

### 4.3 配線手順

**必ず Pi の電源が完全に切れていることを確認してから**、以下の順で:

1. **GND** を最初 (Pin 6 → LCD の GND)
2. **VCC** (Pin 2 = **5V** に注意、Pin 1 の 3.3V ではない)
3. **SDA** (Pin 3 → LCD の SDA)
4. **SCL** (Pin 5 → LCD の SCL)

### 4.4 配線後の物理チェック

電源を入れる **前** に:
- ジャンパー線 4 本がしっかり刺さっているか
- 隣のピンにショートしていないか (特に Pin 1 の 3.3V と Pin 2 の 5V の隣接)
- LCD モジュールに機械的ストレスがかかっていないか

問題なければ Pi の電源を入れる。

### 4.5 LCD バックライトが点灯するはずのタイミング

Pi の電源投入 → 起動中に **バックライト (青 or 緑) が点灯** すれば電源系は正常。
文字は初期状態では表示されない (I2C 通信でデータを送るまでは空)。

**バックライトが点かない場合**:
- VCC 配線を再確認 (5V が来ているか)
- I2C バックパック上の **ジャンパキャップ** が刺さっているか目視
- Nokia の教訓通り、**バックパックのハンダ不良** も疑う (今回のあなたのケース)
- 青いトリマを回してコントラスト調整でも文字が見えないか確認

---

## 5. Phase A: 診断スクリプトで表示確認

本番導入の前に、**表示できる文字コードの範囲** を実機で確認します。

### 5.1 スクリプト転送 (Windows PowerShell)

```powershell
scp -r Z:\afterNK\ESPSARVER\outputs\i2c_lcd_display pi@192.168.11.200:/home/pi/
```

### 5.2 診断スクリプト実行 (Pi)

```bash
cd ~/i2c_lcd_display
bash setup_pi.sh
```

このスクリプトが自動で:
1. I2C 有効化確認
2. `i2cdetect -y 1` で LCD の I2C アドレスをスキャン表示
3. Python venv 作成 + `RPLCD`, `smbus2`, `requests` インストール
4. 診断スクリプト `i2c_lcd_charmap_test.py` を起動

### 5.3 i2cdetect の見方

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- 27 -- -- -- -- -- -- -- --   ← ★ここに 27 と出れば OK
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

- **27** or **3F** が典型的な PCF8574 アドレス
- 全て `--` なら LCD が I2C バスに現れていない → 配線 or 電源問題

**必ずアドレスをメモ** (Phase B で使う)。

### 5.4 診断スクリプトのページ内容 (8 ページ × 5 秒 = 40 秒周期)

| ページ | 内容 | 判定 |
|---|---|---|
| 1 | 情報 (I2C アドレス、行列数) | 表示されれば LCD 動作 |
| 2 | ASCII 0x20-0x6F (英数記号) | 必ず表示されるはず |
| 3 | ASCII 0x70-0x7F (小文字後半 + `~`) | 同上 |
| 4 | 0x80-0x9F | **charmap 依存、表示されない場合あり** (問題なし) |
| 5 | 0xA0-0xDF | **半角カタカナが出るか要確認** (出れば nickname に半角カナ使用可能) |
| 6 | 0xE0-0xFF | 記号・矢印・数式など |
| 7 | サンプル温度表示レイアウト | 本番デザインの予行 |
| 8 | 半角カナ サンプル文 | charmap='A00' 時のみ意味あり |

### 5.5 診断結果の判定

**うまくいったケース (本ガイド作成時の実測)**:
- ページ 1-3, 5-7: 期待通り表示
- ページ 4 (0x80-0x9F): 何も表示なし (charmap='A02' の場合の正常挙動)
- ページ 8: 意味のある表示は出ない (charmap='A02' の場合)

→ **ASCII と半角カナ (0xA0-0xDF) と記号 (0xE0-0xFF) は表示可能**、
   **漢字は物理的に不可**

`Ctrl+C` で診断終了。

---

## 6. Phase B: 本番サービス導入

Phase A の結果で LCD が動くことを確認したら、本番用の常駐サービスをインストール:

### 6.1 本番インストール実行

```bash
cd ~/i2c_lcd_display
bash install_service.sh
```

対話式に:
1. `i2cdetect -y 1` の結果表示 → アドレス再確認
2. 「I2C アドレス」を入力 (例: `0x27`)
3. systemd unit にアドレス反映
4. サービス起動 → `Active: active (running)` を表示

### 6.2 起動後の表示

3 秒間だけ起動メッセージ:
```
+--------------------+
|Temp Monitor Booting|
|Pi IP: 192.168.11.200|
|Dashboard http://.  |
|192.168.11.200:5000/|
+--------------------+
```

その後、本番レイアウトに切替:
```
+--------------------+
|2026/08/07  09:30:45|
|AP+ WAN+ CAM+ 1/2   |
|ESP-A1B2C3 25.3C -55|
|NOW-F73444 29.4C -30|
+--------------------+
```

### 6.3 動作ログ観察

```bash
sudo journalctl -u i2c-lcd-display -f
```

- `LCD initialized at 0x27, 20x4` → 初期化 OK
- `LCD display loop started` → メインループ動作中
- エラーがなければ Ctrl+C で journal 表示だけ抜ける (サービスは動き続ける)

---

## 7. 表示レイアウトと運用中の調整

### 7.1 各行の意味

**Line 1** (日付+時刻):
```
2026/08/07  09:30:45
YYYY/MM/DD  HH:MM:SS
```
Pi のシステム時刻を秒まで表示。`timedatectl` で JST 同期済み前提。

**Line 2** (状態 + ページ番号):
```
AP+ WAN+ CAM+ 1/2
```

- `AP+/-`: hostapd (wlan1 センサー AP) 稼働/停止
- `WAN+/-`: wlan0 (ビル WiFi) 接続/切断
- `CAM+/-`: USB カメラ (/dev/video*) 有無
- 右端:
  - `1/2` (ページ番号) — センサーが 3 台以上ある場合
  - `3sens` (総センサー数) — 2 台以下の場合
  - `FLASK-` — Flask (temperature-server) 停止時の警告

**Line 3-4** (センサー):
```
ESP-A1B2C3 25.3C -55
[  name    ][temp][rssi]
```

- **name** (10 文字): nickname 優先 → sensor_id → device_id
  - MAC ベース device_id (`ESP-XXXXXX`、`NOW-XXXXXX`) なら 10 文字ぴったり
  - nickname に **漢字が含まれれば `.` に置換される** (HD44780 制約)
- **temp** (4 文字 + `C`): `25.3C`、範囲外なら `--.-`
- **rssi** (4 文字): 右詰め `-55`、無しなら `  --`

センサー 3 台以上あれば **5 秒ごとに Line 3-4 がローテ**。

### 7.2 調整可能パラメータ

```bash
sudo systemctl edit i2c-lcd-display
```

エディタで環境変数を追加/変更:

```ini
[Service]
Environment="LCD_I2C_ADDR=0x3F"          # I2C アドレス変更 (0x27 or 0x3F)
Environment="LCD_REFRESH_SEC=1"          # 表示更新間隔 (秒)
Environment="LCD_ROTATE_SEC=8"           # センサーローテーション間隔 (秒)
Environment="LCD_SENSORS_PER_PAGE=2"     # 1 ページのセンサー数
Environment="FLASK_URL=http://localhost:5000"  # Flask URL 変更
```

保存 → 再起動:
```bash
sudo systemctl daemon-reload
sudo systemctl restart i2c-lcd-display
```

### 7.3 nickname の設計指針

漢字が LCD に出せないので、以下のいずれかで運用:

- **A案**: ダッシュボードは漢字、LCD は自動で `.` 置換 (現状の実装)
- **B案**: nickname を全て **10 文字以内の ASCII/半角カナ** で管理 (例: `Reactor-1`, `Outside`, `ATRIUM-2`)
- **C案**: 将来対応 (nickname_ascii フィールド追加、charmap='A00' + 半角カナ変換)

現時点で B案が実用的。ダッシュボードでは分かりやすいラベル、LCD では英字での省略名。

### 7.4 コントラスト調整

LCD バックパックの **青いトリマ (半固定抵抗)** を精密ドライバで回す:
- 時計回りで薄く / 反時計回りで濃く (個体により逆)
- 一周半で最適点あり
- ソフトウェアからは調整不可 (物理調整のみ)

---

## 8. トラブルシューティング

### 8.1 何も表示されない、バックライトも点かない

| 確認事項 | 対処 |
|---|---|
| VCC が 5V に接続されているか | Pin 2 (5V) or Pin 4 (5V) 確認、Pin 1 (3.3V) は誤り |
| GND 接続 | Pin 6 (GND) 確認 |
| バックパック ジャンパ有無 | JP1 にキャップ装着 (無いとバックライト消灯) |
| I2C 有効化 | `ls /dev/i2c-1` で確認、無ければ raspi-config |
| ハンダ不良 (バックパック) | LED 端子の A / K を目視、ハンダブリッジや切れを確認 |
| コントラスト | 青いトリマを回す (デフォルトずれで真っ白/真っ黒可能性) |

### 8.2 バックライト点いているが文字が見えない

**コントラスト調整** (青いトリマを回す)。それでも見えなければ:

```bash
sudo journalctl -u i2c-lcd-display -n 20
```

エラーメッセージを確認。特に `LCD init failed` があれば I2C アドレス不一致。

### 8.3 `LCD init failed: [Errno ...] Remote I/O error`

I2C アドレスが違う。`sudo i2cdetect -y 1` で実際のアドレスを再確認して、systemctl edit で `LCD_I2C_ADDR` を変更。

### 8.4 文字は出るがセンサー行が空 (`?`)

Flask が停止中 or 接続不能:
```bash
curl http://localhost:5000/api/sensors
```

- レスポンスが返る → Nokia 側の bug (journal 確認)
- 接続失敗 → `sudo systemctl status temperature-server`

### 8.5 日付が「1970/01/01」等

Pi の時刻同期問題:
```bash
timedatectl
# NTP=active になっているか、Time zone が Asia/Tokyo か確認

# NTP 有効化
sudo timedatectl set-ntp true
```

### 8.6 センサー名が全て `.` (漢字置換)

nickname に漢字が使われている。ダッシュボードの「表示名管理」タブで、
**LCD 用に半角英字の nickname に変更** (例: 「冷却塔1」 → `Reactor-1`)。

将来的に半角カナ対応するなら charmap='A00' への切替 + Python 側で unicode→cp932
変換ロジック追加。

### 8.7 表示が数秒ごとに一瞬乱れる

I2C バス上に別デバイスがある or ノイズ:
- 他の I2C デバイスと共有時: `i2cdetect -y 1` で確認
- 単独運用時: 配線が長すぎる、電源が不安定など

### 8.8 サービス起動失敗 (`Active: failed`)

```bash
sudo journalctl -u i2c-lcd-display -n 30 --no-pager
```

よくある原因:
- Python venv の破損 → `cd ~/i2c_lcd_display && rm -rf venv && bash setup_pi.sh` で再構築
- RPLCD 未インストール → `./venv/bin/pip install RPLCD smbus2 requests`
- I2C 有効化忘れ → raspi-config → I2C Enable

### 8.9 `Environment` 変更が反映されない

```bash
# override 内容確認
sudo systemctl show i2c-lcd-display | grep -i environment

# systemd をリロード
sudo systemctl daemon-reload
sudo systemctl restart i2c-lcd-display
```

---

## 9. Nokia 5110 からの移行 (該当者向け)

Nokia 5110 モジュールが故障 (今回のケース: バックライトのハンダ不良) or 使い勝手の
悪さで I2C LCD に切り替える場合:

### 9.1 Nokia 側の削除

```bash
sudo systemctl stop nokia-display
sudo systemctl disable nokia-display
sudo rm /etc/systemd/system/nokia-display.service
sudo rm -rf /etc/systemd/system/nokia-display.service.d/
sudo systemctl daemon-reload
rm -rf ~/nokia5110_display
```

Nokia の SPI を無効化するかは任意 (無効化しなくても I2C とは別なので競合しない):
```bash
sudo raspi-config
# Interface Options → SPI → No (Disable)
```

### 9.2 Nokia の物理配線を外す (電源 OFF で)

Nokia の 8 本のジャンパー線を全て抜く。Pi の GPIO は元の状態に戻る。

### 9.3 Nokia のコードを Z: 側に残置

`Z:\afterNK\ESPSARVER\outputs\nokia5110_display\` はそのまま残しておく:
- ハード故障の記録として
- 別 Nokia モジュール入手時の再利用のため
- ドキュメント `outputs/docs/Nokia5110_接続と設置ガイド.md` も同様

### 9.4 I2C LCD 導入 (本ガイドの §3-§6 に進む)

Nokia とは別に、SPI と I2C は独立してるので、共存も可能 (両方使う意味は薄いが)。

---

## 10. 完全撤去手順

I2C LCD が不要になった場合:

```bash
# サービス停止・無効化
sudo systemctl stop i2c-lcd-display
sudo systemctl disable i2c-lcd-display

# systemd unit 削除
sudo rm /etc/systemd/system/i2c-lcd-display.service
sudo rm -rf /etc/systemd/system/i2c-lcd-display.service.d/
sudo systemctl daemon-reload

# アプリファイル削除
rm -rf ~/i2c_lcd_display
```

物理配線も外し、Pi をシャットダウンしてジャンパー線を抜く。

I2C を無効化する場合 (他の I2C デバイスが無ければ):
```bash
sudo raspi-config
# Interface Options → I2C → No (Disable)
```

---

## 関連ドキュメント

- `outputs/i2c_lcd_display/README.md` — 技術リファレンス (パラメータ、コード詳細)
- `outputs/i2c_lcd_display/i2c_lcd_display.py` — 本番スクリプト
- `outputs/i2c_lcd_display/i2c_lcd_charmap_test.py` — 診断スクリプト
- `outputs/docs/Nokia5110_接続と設置ガイド.md` — 前システム (故障で移行)
- `outputs/docs/RaspberryPi_セットアップガイド.md` — Pi 全体構築
- `outputs/README.md` — システム全体概要
