# Nokia 5110 表示機能

Raspberry Pi 本体に Nokia 5110 (PCD8544) モノクロ LCD 84x48 を取り付けて、温度モニタリング
システムの主要ステータスを一目で確認できるようにする機能。

## 表示内容

```
+-------------------------+
|12/31 15:30    AP◆       |  ← 日時 + AP (hostapd) 稼働状態
|WAN:o   CAM 📷          |  ← wlan0 状態 + USB カメラ有無
+-------------------------+
|冷却塔1   25.3° ▮▮▮      |
|外気温    18.5° ▮▮▮▮     |  ← nickname (最大 3 台) + 温度 + RSSI バー
|受電盤    30.2° ▮▮       |
+-------------------------+  超過分は 5 秒ごとにローテーション
```

## 必要ハードウェア

- Raspberry Pi (SPI 有効化可能なモデル、Pi 4B 前提で検証)
- Nokia 5110 LCD モジュール (PCD8544 コントローラ、84x48px、白/青バックライト付きが一般的)
- ジャンパー線 8 本
- 抵抗 (バックライト直結する場合、電流制限用に 220-330Ω)

秋月電子等で入手可能。数百円。

## 配線 (Pi 40-pin ヘッダ、BCM 番号)

| Nokia 5110 | Pi Pin | Pi GPIO (BCM) | 用途 |
|---|---|---|---|
| VCC | Pin 1 | 3.3V | 電源 |
| GND | Pin 6 | GND | グラウンド |
| DIN | Pin 19 | GPIO10 (MOSI) | SPI データ入力 |
| CLK | Pin 23 | GPIO11 (SCLK) | SPI クロック |
| DC  | Pin 16 | GPIO23 | データ/コマンド切替 |
| CE  | Pin 24 | GPIO8 (SPI0 CE0) | チップ選択 |
| RST | Pin 22 | GPIO25 | リセット |
| BL (LED) | Pin 1 (3.3V) 直結 or Pin 12 (GPIO18) | - | バックライト |

> BL を GPIO18 に繋ぐと Python 側から on/off できるが、常時点灯なら 3.3V 直結で OK。
> **注意**: 生の LED は電流制限抵抗を挟むこと (220-330Ω)。モジュール品によっては
> 抵抗内蔵で直結できるものもあるので実物を確認。

## Pi 側事前準備

### 1. SPI 有効化

```bash
sudo raspi-config
# Interface Options → SPI → Enable → Reboot
```

再起動後、以下で確認:
```bash
lsmod | grep spi_bcm
# → spi_bcm2835 が表示されれば OK
```

### 2. スクリプト配置

Windows PowerShell から:
```powershell
scp -r Z:\afterNK\ESPSARVER\outputs\nokia5110_display pi@192.168.11.200:/home/pi/
```

### 3. セットアップスクリプト実行 (Pi 側 SSH)

```bash
cd ~/nokia5110_display
sudo bash setup_pi.sh
```

これで:
1. SPI 確認
2. `fonts-noto-cjk` (常用漢字対応), `fonts-mplus`, python3-venv, libjpeg-dev 等インストール
3. Python venv 作成、`luma.lcd`, `Pillow`, `requests`, `RPi.GPIO`, `spidev` インストール
4. systemd unit `/etc/systemd/system/nokia-display.service` 配置
5. サービス起動

### 4. 動作確認

```bash
# サービス状態
sudo systemctl status nokia-display --no-pager

# ログ観察
sudo journalctl -u nokia-display -f
```

Nokia LCD に表示が出れば成功。ダッシュボードの Flask API を叩いてデータを取得しているので、
Flask (temperature-server) が動いていることが前提。

## 表示調整パラメータ (systemd unit の Environment= で変更)

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `FLASK_URL` | `http://localhost:5000` | Flask のエンドポイント |
| `DISPLAY_REFRESH_SEC` | `2` | 表示全体の更新間隔 (秒) |
| `DISPLAY_ROTATE_SEC` | `5` | センサーローテーション間隔 (秒) |
| `DISPLAY_SENSORS_PER_PAGE` | `3` | 一度に表示するセンサー数 |
| `FONT_ASCII_SIZE` | `8` | 日時・状態用 ASCII フォントサイズ |
| `FONT_KANJI_SIZE` | `10` | センサー名用 漢字フォントサイズ |
| `NOKIA_CONTRAST` | `60` | コントラスト (0-127、暗いと下げる) |
| `NOKIA_GPIO_DC` | `23` | DC ピン (BCM) |
| `NOKIA_GPIO_RST` | `25` | RST ピン (BCM) |

変更する場合:
```bash
sudo systemctl edit nokia-display  # override 作成
# または /etc/systemd/system/nokia-display.service を直接編集
sudo systemctl daemon-reload
sudo systemctl restart nokia-display
```

## アイコン仕様

- **AP アイコン**: 塗りつぶし四角 = 稼働、枠のみ = 停止
- **CAM アイコン**: レンズが塗りつぶし = カメラ接続あり、枠のみ = なし
- **RSSI バー**: 4 段階のスタッキングバー
  - `▮▮▮▮` : RSSI > -50 dBm (excellent)
  - `▮▮▮_` : -50 〜 -60 dBm (good)
  - `▮▮__` : -60 〜 -70 dBm (fair)
  - `▮___` : -70 〜 -80 dBm (weak)
  - `____` : < -80 dBm or 不明 (base line のみ)

## 日本語表示について

- `fonts-noto-cjk` パッケージ (Noto Sans CJK JP) を使用
- 10 ピクセル程度でも常用漢字は読める (見づらいがなんとか)
- 漢字が多い nickname は 5 文字程度で切り詰め
- カタカナ or 短い漢字を推奨 (例: 「冷却塔1」「外気温」「受電盤」「圧縮機」)

フォントが読みにくい場合は `FONT_KANJI_SIZE=12` に上げて試行 (センサー行数減る)。

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| 表示真っ白 or 真っ黒 | コントラスト調整不足 | `NOKIA_CONTRAST=40〜80` で試行 |
| SPI エラー | SPI 未有効化 | raspi-config で SPI Enable → 再起動 |
| ImportError: luma | pip install 失敗 | venv 再構築、requirements.txt 確認 |
| 漢字が表示されない (□) | フォント未インストール | `sudo apt install fonts-noto-cjk` |
| Flask に接続できないログ | temperature-server が停止 | `sudo systemctl status temperature-server` |
| 表示が更新されない | サービス停止 | `sudo systemctl restart nokia-display` |
| センサーは温度取れているが Nokia に出ない | JSON フィールド不一致 | `curl localhost:5000/api/sensors` で内容確認、rssi キー等 |

## 関連ドキュメント

- `outputs/README.md` — システム全体概要
- `outputs/docs/RaspberryPi_セットアップガイド.md` — Pi 全体構築
- `outputs/temperature_server_full/` — Flask サーバー本体
