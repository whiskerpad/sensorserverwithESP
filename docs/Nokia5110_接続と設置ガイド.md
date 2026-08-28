# Nokia 5110 表示装置 接続・設置 実施ガイド

Raspberry Pi 4B に Nokia 5110 (PCD8544) モノクロ LCD (84×48px) を取り付けて、
温度モニタリングシステムの主要ステータスを本体で確認できるようにする手順書。

**対応時間の目安**: 配線 15 分 + Pi 側ソフト導入 5 分 + 動作確認 5 分 = **合計 30 分程度**。

---

## 目次

1. [必要な材料](#1-必要な材料)
2. [事前準備 (電源 OFF で作業)](#2-事前準備-電源-off-で作業)
3. [Pi 側 SPI 有効化 (Nokia 接続前)](#3-pi-側-spi-有効化-nokia-接続前)
4. [物理配線 (電源 OFF 厳守)](#4-物理配線-電源-off-厳守)
5. [ソフトウェア導入](#5-ソフトウェア導入)
6. [動作確認](#6-動作確認)
7. [表示調整](#7-表示調整)
8. [トラブルシューティング](#8-トラブルシューティング)

---

## 1. 必要な材料

| 項目 | 個数 | 備考 |
|---|---|---|
| Nokia 5110 LCD モジュール | 1 | PCD8544 コントローラ搭載、白バックライトが標準 |
| ジャンパー線 (メス-メス、10cm 程度) | 8 本 | ブレッドボードなら オス-メス |
| 220-330Ω 抵抗 | 0-1 本 | BL (バックライト) を GPIO 経由で使う場合のみ (3.3V 直結なら不要) |
| Raspberry Pi 4B | 1 | 稼働中の Pi でよい |

Nokia 5110 モジュールの端子並び (裏面):

```
[ RST ] [ CE ] [ DC ] [ DIN ] [ CLK ] [ VCC ] [ BL ] [ GND ]
   1      2       3       4       5       6       7      8
```

※ 個体差あり。**モジュールの基板シルクを目視確認** して端子順を必ず特定してください。

---

## 2. 事前準備 (電源 OFF で作業)

### 2.1 Pi のシャットダウン

```bash
sudo shutdown -h now
```

**LED (緑) が完全に消灯するまで待ってから** 電源アダプタを抜く。稼働中の SPI ピンに
配線するとハード破損の恐れがあります。

### 2.2 作業机の準備

- 静電気対策 (可能なら アルミホイル やアース紐)
- 40 ピンヘッダのピン番号を確認できるレファレンス (下記の図)

Pi 4B の 40 ピンヘッダ配置 (Pi のロゴを上、USB を右にした向き):

```
             (Pi 上端)
            +----------+
   3.3V →  1  ● ● 2  ← 5V
   GPIO2 → 3  ● ● 4  ← 5V
   GPIO3 → 5  ● ● 6  ← GND      ★ GND
    ...
  GPIO18 → 12  ● ● 11
   GPIO25 → 22  ● ● 21          ★ RST
   GPIO23 → 16  ● ● 15          ★ DC
     GND → 14  ● ● 13
              ●
  GPIO10 → 19  ● ● 20          ★ DIN (MOSI)
     GND → 20  ● ● 19
  GPIO11 → 23  ● ● 24          ★ CLK (SCLK) と CE
    GPIO8 → 24  ● ● 25          ★ CE (SPI0 CE0)
            +----------+
             (Pi 下端)
```

**★ が Nokia 用に使うピン (合計 8 ピン)**

---

## 3. Pi 側 SPI 有効化 (Nokia 接続前)

### 3.1 raspi-config で SPI 有効化

Pi の電源を入れて SSH ログイン:

```bash
sudo raspi-config
```

メニューで:
1. `3 Interface Options`
2. `I4 SPI`
3. `Yes` (Enable SPI interface)
4. `Ok`
5. `Finish` → Reboot するか聞かれたら `Yes`

再起動後に SSH 再接続。

### 3.2 SPI 有効化確認

```bash
lsmod | grep spi_bcm
```

**期待出力**:
```
spi_bcm2835            32768  0
```

何も出なければ SPI 未有効。3.1 をやり直す。

### 3.3 デバイスファイル確認

```bash
ls -la /dev/spidev*
```

**期待出力**:
```
crw-rw---- 1 root spi 153, 0 ... /dev/spidev0.0
crw-rw---- 1 root spi 153, 1 ... /dev/spidev0.1
```

`spidev0.0` があれば SPI OK。

### 3.4 pi ユーザーを spi グループに追加

```bash
groups pi | grep spi
```

`spi` が含まれていなければ:
```bash
sudo usermod -a -G spi pi
```

**追加後は再ログインしないと反映されない**。SSH を抜けて入り直す。

---

## 4. 物理配線 (電源 OFF 厳守)

### 4.1 再度シャットダウン

```bash
sudo shutdown -h now
```

LED 消灯 → 電源アダプタを抜く。

### 4.2 配線対応表

| Nokia 5110 | 接続先 Pi ピン | Pi GPIO (BCM) | 用途 |
|---|---|---|---|
| **VCC** | Pin 1 | 3.3V | 電源 (必ず 3.3V、5V は破損) |
| **GND** | Pin 6 (or 9, 14, 20, 25, 30, 34, 39 のいずれか) | GND | グラウンド |
| **DIN** | Pin 19 | GPIO10 | SPI MOSI (Pi → LCD データ) |
| **CLK** | Pin 23 | GPIO11 | SPI SCLK (クロック) |
| **DC** | Pin 16 | GPIO23 | データ/コマンド切替 |
| **CE** | Pin 24 | GPIO8 | SPI0 CE0 (チップ選択) |
| **RST** | Pin 22 | GPIO25 | リセット |
| **BL** | Pin 1 (3.3V) 直結 or Pin 12 (GPIO18) | - | バックライト |

### 4.3 配線手順 (推奨順序)

**必ず電源が完全に切れていることを確認してから**、以下の順で配線:

1. **GND** を最初に接続 (Pin 6 と Nokia の GND)
   - グラウンドを先に共通化してから信号線を繋ぐのが電子工作の定石
2. **VCC** を接続 (Pin 1 と Nokia の VCC) ← 5V ピン (Pin 2/4) に間違えて挿さないよう注意
3. **RST** を接続 (Pin 22 と Nokia の RST)
4. **CE** を接続 (Pin 24 と Nokia の CE)
5. **DC** を接続 (Pin 16 と Nokia の DC)
6. **DIN** を接続 (Pin 19 と Nokia の DIN)
7. **CLK** を接続 (Pin 23 と Nokia の CLK)
8. **BL** を接続 (Pin 1 の 3.3V に直結、または Pin 12 GPIO18 経由で 330Ω 抵抗を挟んで)

**BL (バックライト) の注意**:
- モジュールに電流制限抵抗が実装済のものは 3.3V 直結で OK
- 抵抗なしの生 LED タイプは **必ず 220-330Ω 抵抗を挟む** (直結すると LED 焼損)
- 実物を見て、Nokia 基板の BL ピン付近に SMD 抵抗が載っているか確認

### 4.4 配線確認

配線後、電源を入れる **前** に:
- ジャンパー線がしっかり刺さっているか (ぐらつきなし)
- 隣のピンにショートしていないか (特に 3.3V と 5V の隣接注意)
- Nokia モジュールに機械的ストレスがかかっていないか

問題なければ Pi の電源を入れる。

---

## 5. ソフトウェア導入

Pi の電源投入 → SSH ログイン後:

### 5.1 スクリプト一式を Pi に配置

**Windows PowerShell で**:
```powershell
scp -r Z:\afterNK\ESPSARVER\outputs\nokia5110_display pi@192.168.11.200:/home/pi/
```

### 5.2 セットアップスクリプト実行

**Pi の SSH で**:
```bash
cd ~/nokia5110_display
sudo bash setup_pi.sh
```

このスクリプトが以下を自動実行:
1. SPI 有効化確認 (§3 実施済みなら OK と出る)
2. `fonts-noto-cjk` (常用漢字対応), `fonts-mplus`, python3-venv, ビルド依存インストール
3. Python venv 作成 (`~/nokia5110_display/venv/`)
4. `luma.lcd`, `Pillow`, `requests`, `RPi.GPIO`, `spidev` インストール
5. systemd unit `nokia-display.service` 配置と `enable`
6. サービス起動

### 5.3 セットアップスクリプト出力の確認

期待される最終出力:
```
[1/6] SPI インターフェース有効化確認...
  SPI OK
[2/6] 日本語フォント インストール...
   ...
[3/6] Python venv 作成...
[4/6] Python 依存インストール...
[5/6] systemd unit 反映...
[6/6] サービス起動...
● nokia-display.service - Nokia 5110 Display for Temperature Monitor
     Loaded: loaded (/etc/systemd/system/nokia-display.service; enabled; ...)
     Active: active (running) since ...
```

`Active: active (running)` が出れば OK。

**エラーが出たら §8 トラブルシューティング** を参照。

---

## 6. 動作確認

### 6.1 表示が出るか

Nokia 5110 LCD に文字が表示されているか目視確認。

**期待される画面** (数秒後):
```
+-------------------+
|07/31 15:30    AP■ |
|WAN:o    CAM ▢    |
|─────────────      |
|冷却塔1  25.3° ▮▮▮|
|外気温   18.5° ▮▮  |
+-------------------+
```

- 日時が現在時刻
- AP アイコンが塗りつぶし (hostapd 稼働中)
- WAN:o or WAN:x (wlan0 の接続状態)
- CAM アイコン (USB カメラ有無)
- センサー行にデータ

### 6.2 ログ確認

```bash
sudo journalctl -u nokia-display -f
```

- `Nokia 5110 display started` の後、エラーなくループしていれば正常
- `Ctrl+C` で終了 (journalctl の表示を止めるだけ、サービスは動き続ける)

### 6.3 表示に問題があれば §7 の調整、または §8 のトラブル対処へ

---

## 7. 表示調整

すべて systemd unit の `Environment=` で設定変更可能。

### 7.1 コントラストが薄い or 濃すぎる

```bash
sudo systemctl edit nokia-display
```

エディタが開くので:
```
[Service]
Environment="NOKIA_CONTRAST=50"
```
を追加 (デフォルト 60、範囲 0-127、薄いと表示が薄い、濃いと真っ黒)。

保存後:
```bash
sudo systemctl restart nokia-display
```

### 7.2 更新が速すぎる/遅すぎる

```bash
sudo systemctl edit nokia-display
```

```
[Service]
Environment="DISPLAY_REFRESH_SEC=3"
Environment="DISPLAY_ROTATE_SEC=8"
```

### 7.3 センサー行数を増やしたい (フォント小さくなる)

```bash
sudo systemctl edit nokia-display
```

```
[Service]
Environment="DISPLAY_SENSORS_PER_PAGE=4"
Environment="FONT_KANJI_SIZE=8"
```

**注意**: フォント 8px だと常用漢字は判読困難、カタカナ推奨に切替。

### 7.4 センサー行数を減らしたい (フォント大きくなる)

```
[Service]
Environment="DISPLAY_SENSORS_PER_PAGE=2"
Environment="FONT_KANJI_SIZE=12"
```

### 7.5 変更反映

```bash
sudo systemctl daemon-reload
sudo systemctl restart nokia-display
```

---

## 8. トラブルシューティング

### 8.1 何も表示されない

| 確認事項 | コマンド | 対処 |
|---|---|---|
| サービス起動確認 | `sudo systemctl status nokia-display` | 停止していれば restart |
| エラーログ | `sudo journalctl -u nokia-display -n 30` | エラー内容を確認 |
| SPI 有効化 | `lsmod | grep spi_bcm` | 未有効なら §3.1 |
| 配線 (VCC/GND) | 目視 | 3.3V が来ているか、GND がしっかり接続 |
| コントラスト | `Environment="NOKIA_CONTRAST=40"` | 極端に薄いと真っ白に見える |

### 8.2 表示が真っ白 or 真っ黒

コントラスト調整。`NOKIA_CONTRAST` を 30-80 の範囲で試行:
```bash
sudo systemctl edit nokia-display
# [Service]
# Environment="NOKIA_CONTRAST=45"
sudo systemctl daemon-reload
sudo systemctl restart nokia-display
```

### 8.3 表示が化ける (ノイズだらけ)

- SPI クロックが速すぎる可能性
- 配線が長すぎる (10cm 以内推奨)
- 電源が不安定 (別 5V→3.3V レギュレータから給電を試す)

### 8.4 漢字が □ になる (フォント無し)

```bash
sudo apt install -y fonts-noto-cjk fonts-mplus
sudo systemctl restart nokia-display
```

### 8.5 ImportError: luma / spidev

```bash
cd ~/nokia5110_display
./venv/bin/pip install --force-reinstall luma.lcd Pillow spidev RPi.GPIO
sudo systemctl restart nokia-display
```

### 8.6 センサー表示が全て "--.-"

Flask との通信不能:
```bash
curl http://localhost:5000/api/sensors
```
何か返れば Nokia 側の JSON パース、返らなければ Flask 側の問題 (temperature-server 停止など)。

### 8.7 バックライトが眩しい / 消したい

BL を GPIO18 経由で接続していれば Python から制御可能。3.3V 直結の場合は物理的に BL 線を抜くか、
Nokia モジュール裏の BL ジャンパを外す (モジュール品による)。

### 8.8 電源投入時に一瞬だけ表示が出て消える

- サービスが起動失敗して systemd が停止させている可能性
- `sudo journalctl -u nokia-display -n 50` でエラー確認
- venv のパス問題、フォントパス問題を疑う

### 8.9 SPI Permission denied

```bash
groups pi | grep spi
# spi が無ければ:
sudo usermod -a -G spi pi
# 再ログイン必須
exit
```
再度 SSH して再確認。

---

## 9. 完全撤去手順

Nokia が不要になった場合:

```bash
sudo systemctl stop nokia-display
sudo systemctl disable nokia-display
sudo rm /etc/systemd/system/nokia-display.service
sudo systemctl daemon-reload

# ファイル削除
rm -rf ~/nokia5110_display
```

物理配線も外し、Pi をシャットダウンしてジャンパー線を抜く。

---

## 関連ドキュメント

- `outputs/nokia5110_display/README.md` — スクリプト側の技術リファレンス
- `outputs/nokia5110_display/nokia5110_display.py` — 本体スクリプト
- `outputs/docs/RaspberryPi_セットアップガイド.md` — Pi 全体構築
- `outputs/README.md` — システム全体概要
