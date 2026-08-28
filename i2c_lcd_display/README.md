# I2C 20×4 キャラクター LCD 診断 (半角カナ表示可否の実機確認)

## 目的

- HD44780 系 I2C キャラクター液晶 (20 列 × 4 行) の表示能力を実機で確認
- 5 秒ローテで **全キャラコード** を順に表示
- 半角カタカナが表示できるか判定 (charmap 'A00' モジュール前提)
- 温度表示レイアウトのサンプルも見せて視認性を評価

## 必要なもの

- Raspberry Pi (I2C 有効化可能なモデル)
- 20×4 キャラ LCD + I2C バックパック (PCF8574、5V モジュール標準)
- ジャンパー線 4 本のみ

## 配線 (I2C は 4 本だけ!)

| LCD ピン | Pi ピン | GPIO |
|---|---|---|
| VCC | Pin 2 (5V) | - |
| GND | Pin 6 (GND) | - |
| SDA | Pin 3 | GPIO2 (SDA) |
| SCL | Pin 5 | GPIO3 (SCL) |

**注意**:
- LCD は 5V 版と 3.3V 版がある。**必ず実物の動作電圧を確認**してから接続
- I2C バックパックのボリューム (10kΩ 可変抵抗) を回してコントラスト調整可

## 事前準備 (Pi 側)

### I2C 有効化

```bash
sudo raspi-config
# Interface Options → I2C → Enable → Reboot
```

再起動後、確認:
```bash
ls /dev/i2c-1
# → /dev/i2c-1 が表示されれば OK
```

### スクリプト転送

Windows PowerShell:
```powershell
scp -r Z:\afterNK\ESPSARVER\outputs\i2c_lcd_display pi@192.168.11.200:/home/pi/
```

## 診断実行

Pi 側:
```bash
cd ~/i2c_lcd_display
bash setup_pi.sh
```

setup_pi.sh が:
1. I2C 有効化確認
2. `i2cdetect -y 1` で接続デバイス一覧表示 (アドレスをメモしておく)
3. Python venv 作成 + `RPLCD` インストール
4. 診断スクリプト起動

## 期待される I2C デバイス検出

`i2cdetect -y 1` の出力例:
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- --
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
30: -- -- -- -- -- -- -- 27 -- -- -- -- -- -- -- --   ← 0x27 が LCD
```

- **0x27** or **0x3F** のいずれかが典型的
- 何も表示されなければ配線 or 電源問題

## ページ内容 (5 秒 × 8 ページ = 40 秒で 1 周)

| ページ | 内容 |
|---|---|
| 1 | 情報 (I2C アドレス、行列数) |
| 2 | ASCII 0x20-0x6F (英数記号) |
| 3 | ASCII 0x70-0x7F (小文字後半 + ~) |
| 4 | 0x80-0x9F (charmap 依存、多くは空/表示不可) |
| 5 | **0xA0-0xDF (期待: 半角カタカナ)** |
| 6 | 0xE0-0xFF (記号・数式・矢印等) |
| 7 | サンプル温度表示 レイアウト (`ESP-A1B2 25.3C -55`) |
| 8 | 半角カナサンプル (charmap='A00' モジュール時のみ有効) |

## 判定基準

- **ASCII (ページ 2-3)**: 必ず表示できる (できなければ配線 or I2C アドレス問題)
- **半角カナ (ページ 5)**: モジュールの CGROM 依存
  - `charmap='A00'` (日本語版 CGROM) → 0xA0-0xDF に半角カタカナが表示
  - `charmap='A02'` (欧州版 CGROM) → 半角カタカナは無い (別記号)
- モジュール仕様書か、実機で確認

## charmap の切替 (実物を見てから)

診断結果で:
- ページ 5 に **半角カナが表示された** → `charmap='A00'` のままで OK
- ページ 5 が空白・変な記号 → `charmap='A02'` に変更してみる

変更方法: `i2c_lcd_charmap_test.py` の `CharLCD(..., charmap='A00', ...)` を
`charmap='A02'` に書換えて再実行。

## 実物で確認したい 3 点

1. I2C アドレス (0x27, 0x3F, 他)
2. ASCII は表示できるか
3. 半角カナ (ページ 5) が読めるか

これらが分かれば、次に本番用の LCD 表示スクリプトを設計します。

---

## 本番用表示スクリプト (診断で動作確認後)

診断で ASCII と半角カナ (0xA0-0xDF) の表示可否が確認できたら、本番用スクリプトを
インストール:

### 1. インストール実行

Pi 側で:
```bash
cd ~/i2c_lcd_display
bash install_service.sh
```

対話式:
1. `i2cdetect -y 1` の結果表示 (アドレスを再確認)
2. I2C アドレス入力 (0x27 or 0x3F 等)
3. systemd unit に反映 + サービス起動

### 2. 表示レイアウト

```
+--------------------+
|2026/08/07  09:30:45|  ← Line 1: 日付 + 時刻
|AP+ WAN+ CAM+ 1/2   |  ← Line 2: 状態 + ページ (or センサー数)
|ESP-A1B2C3 25.3C -55|  ← Line 3: センサー 1 (rotate)
|NOW-F73444 29.4C -30|  ← Line 4: センサー 2
+--------------------+
```

### 3. 表示内容の説明

**Line 1** (日付+時刻): 秒まで実時刻。

**Line 2** (状態):
- `AP+` / `AP-`: hostapd (wlan1 AP) 稼働/停止
- `WAN+` / `WAN-`: wlan0 (ビル WiFi) 接続/切断
- `CAM+` / `CAM-`: USB カメラ (/dev/video*) 有無
- 右端: `1/2` (ページ番号) or `3sens` (総センサー数) or `FLASK-` (Flask 停止時)

**Line 3-4** (センサー):
- device_id (10 文字、`ESP-XXXXXX` or `NOW-XXXXXX`) + 温度 (`25.3C`) + RSSI (`-55`)
- センサーが 3 台以上あれば 5 秒ごとにローテ
- nickname が設定されていれば nickname を優先 (10 文字で切詰め)
- **nickname に漢字が含まれる場合は '.' に置換される** (HD44780 の CGROM 制約)

### 4. 調整パラメータ (systemctl edit)

```bash
sudo systemctl edit i2c-lcd-display
```

環境変数の書換え:
```ini
[Service]
Environment="LCD_I2C_ADDR=0x3F"        # I2C アドレス変更
Environment="LCD_REFRESH_SEC=1"        # 更新間隔
Environment="LCD_ROTATE_SEC=8"         # ローテ間隔
Environment="LCD_SENSORS_PER_PAGE=2"   # ページあたりセンサー数
```

保存後:
```bash
sudo systemctl restart i2c-lcd-display
```

### 5. トラブルシューティング

| 症状 | 対処 |
|---|---|
| 何も表示されない | `sudo journalctl -u i2c-lcd-display -n 20` でエラー確認 |
| `LCD init failed` | I2C アドレスが違う (`i2cdetect -y 1` で再確認) |
| センサーが '?' 連続 | Flask 停止中 (`sudo systemctl status temperature-server`) |
| 日時が --/--/-- | Pi の時刻同期問題 (`timedatectl` 確認) |
| 特定センサーが表示されない | 3 台以上ならローテしているので 5 秒待つ |
| 漢字 nickname が '.' | HD44780 は漢字不可、ASCII/カナで代替名を管理画面で設定 |

### 6. 撤去

```bash
sudo systemctl stop i2c-lcd-display
sudo systemctl disable i2c-lcd-display
sudo rm /etc/systemd/system/i2c-lcd-display.service
sudo systemctl daemon-reload
```

---

## 拡張機能 (2026-08-07 追加)

### 1. 半角カナ nickname 対応

ダッシュボードで nickname に **全角カタカナ** を設定できるようになりました:
- `冷却塔1` → 漢字は `.` 置換 (`.....1`)
- `レイキャクトウ1` (全角カナ) → **`ﾚｲｷｬｸﾄｳ1`** (半角化して LCD 表示)

jaconv ライブラリで全角→半角変換 → HD44780 の 0xA1-0xDF (半角カナ) にマッピング。

**推奨命名例**:
| ダッシュボード (nickname) | LCD 表示 (半角化後) |
|---|---|
| レイキャクトウ1 | ﾚｲｷｬｸﾄｳ1 |
| ソトキオン | ｿﾄｷｵﾝ |
| ジュデンバン | ｼﾞｭﾃﾞﾝﾊﾞﾝ |
| Reactor-1 (ASCII) | Reactor-1 |
| 冷却塔1 (漢字) | .....1 (代替) |

### 2. RSSI バー アイコン (CGRAM slot 0-4)

数値 `-55` の代わりに **WiFi 風の 4 段階バー** で視覚化:

| RSSI | バー数 | 意味 |
|---|---|---|
| > -50 dBm | ▂▃▅▇ (4 段) | excellent |
| -50 〜 -60 | _▃▅▇ (3 段) | good |
| -60 〜 -70 | __▅▇ (2 段) | fair |
| -70 〜 -80 | ___▇ (1 段) | weak |
| < -80 or none | ____ (empty) | poor |

### 3. カスタムアイコン (CGRAM slot 5-7)

| アイコン | Slot | 表示条件 |
|---|---|---|
| 📷 カメラ (小さいカメラ pixmap) | 5 | `/dev/video*` 存在時 |
| 📡 AP (アンテナ塔) | 6 | hostapd 稼働時 |
| 🌐 WLAN (地球儀風) | 7 | wlan0 接続時 |

`AP+/CAM+` の "+" 部分がアイコンに置換されます (未動作時は空白)。

### 拡張レイアウト (更新後)

```
+--------------------+
|2026/08/07  09:30:45|  ← Line 1: 日付+時刻
|AP[📡] WAN[🌐] CAM[📷] 1/2|  ← Line 2: アイコン化された状態
|ﾚｲｷｬｸﾄｳ1   25.3C [▂▃▅▇]|  ← Line 3: 半角カナ nickname + RSSI バー
|ｿﾄｷｵﾝ      29.4C [__▅▇]|  ← Line 4:
+--------------------+
```

### 拡張機能の反映

```bash
cd ~/i2c_lcd_display

# 1) 更新版 i2c_lcd_display.py + requirements.txt を Pi に scp
# (Windows から: scp Z:\afterNK\ESPSARVER\outputs\i2c_lcd_display\i2c_lcd_display.py pi@...:/home/pi/i2c_lcd_display/)
# (同じく requirements.txt も)

# 2) jaconv インストール + サービス再起動
bash upgrade_features.sh
```

または個別に:
```bash
./venv/bin/pip install jaconv
sudo systemctl restart i2c-lcd-display
```

### ログ確認

```bash
sudo journalctl -u i2c-lcd-display -n 20
```

期待される追加行:
```
CGRAM: 5 RSSI bars + camera + AP + WLAN icons
jaconv available: True
```

`jaconv available: False` の場合は `pip install jaconv` を再実行。

### CGRAM の使い果たしについて

HD44780 の CGRAM は **8 スロットが最大**。今回の実装で全 8 スロット使用:
- Slot 0-4: RSSI バー 5 段階
- Slot 5: カメラ
- Slot 6: AP
- Slot 7: WLAN

**新しいカスタム文字は追加できません**。追加する場合は既存のどれかを差替え。
