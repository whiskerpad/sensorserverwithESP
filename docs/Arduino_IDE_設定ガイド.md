# Arduino IDE 設定ガイド (ESP-WROOM-02 生チップ書き込み)

秋月電子通商「ESP-WROOM-02 DIP 化キット」に FTDI USB シリアル変換だけで
Arduino スケッチを書き込むための設定手順を網羅した文書。NodeMCU や Wemos D1 の
ような書き込み補助回路が無い前提。

## 対象読者・想定環境

- ESP-WROOM-02 (技適認証あり、Espressif R 201-160606) を単体で使う
- 書き込みは **FTDI USB シリアル変換 (3.3V ロジック)** で実施
- Arduino IDE 1.8.x または 2.x (2.x 推奨)
- Windows 10/11 (macOS/Linux でもほぼ同じ)

---

## 1. 事前準備

### 1.1 ESP8266 ボードマネージャの導入

Arduino IDE の環境設定 (`ファイル → 環境設定 → 追加のボードマネージャの URL`) に
以下を追加:

```
https://arduino.esp8266.com/stable/package_esp8266com_index.json
```

その後 `ツール → ボード → ボードマネージャ` から `esp8266` を検索し
**3.1.2 以降** (2026 時点最新推奨) をインストール。

### 1.2 必要ライブラリ (`ツール → ライブラリの管理`)

| ライブラリ | 最低バージョン | 用途 |
|---|---|---|
| OneWire | 2.3.x 以上 | DS18B20 1-Wire 通信 |
| DallasTemperature | 3.9.x 以上 | DS18B20 温度取得 API |
| ArduinoJson | 6.21.x (v6 系) | JSON ペイロード生成 |

**注意**: ArduinoJson v7 系は API が破壊的に変わっているため、本プロジェクトは
v6 系 (`^6.21.x`) を指定して使用。

### 1.3 FTDI ドライバ

USB シリアル変換の CH340 系または FTDI FT232 系のドライバを PC にインストール。
Windows は挿すと自動認識するが、認識しなければ以下:
- CH340: WCH 公式サイト https://www.wch-ic.com/downloads/CH341SER_ZIP.html
- FTDI: https://ftdichip.com/drivers/vcp-drivers/

デバイスマネージャで `COM11` などのポート番号を確認。

---

## 2. Arduino IDE のボード設定 (最重要)

`ツール` メニューから以下を **1 つずつ確認しながら** 設定する。ESP-WROOM-02 で
不具合になりやすい項目は 🚨 マークを付けた。

| 設定項目 | 値 | 補足 |
|---|---|---|
| **ボード** | `Generic ESP8266 Module` | 🚨 NodeMCU 等ではなくこれ。ピン別名記号 `D4` 等は使えず、GPIO 番号を直接書く必要あり |
| **ポート** | `COM11` (Windows) 等 | FTDI が接続されたポート |
| Upload Speed | `115200` | 慣れたら 460800 まで上げてもよいが、生 ESP は 115200 が安定 |
| Crystal Frequency | `26 MHz` | ESP-WROOM-02 は 26MHz 水晶 (40MHz は他モジュール向け) |
| Debug port | `Disabled` | 本番実装では無効 |
| **Flash Size** | 🚨 **`4MB (FS:2MB OTA:~1019KB)`** | ESP-WROOM-02 は 32Mbit=4MB フラッシュ搭載。1MB を選ぶと SPIFFS/LittleFS 領域配置が誤る |
| C++ Exceptions | `Disabled (new aborts on oom)` | 例外は使わない (バイナリ肥大化回避) |
| **Flash Frequency** | `40MHz` | 標準。80MHz は電源品質良好時のみ |
| **Flash Mode** | 🚨 **`DOUT (compatible)`** | ESP-WROOM-02 は DOUT。DIO を選ぶと `head packet error` で起動しない個体あり |
| lwIP Variant | `v2 Lower Memory` | メモリ節約版 |
| Builtin Led | `2` | ESP-WROOM-02 の内蔵 LED は GPIO2 |
| Debug Level | `None` | 本番実装では無効 |
| MMU | `32KB cache + 32KB IRAM (balanced)` | 標準 |
| Non-32-Bit Access | `Use pgm_read macros for IRAM/PROGMEM` | 標準 |
| **Reset Method** | 🚨 **`no dtr (aka ck)`** | 生 ESP-WROOM-02 で最重要。詳細は §4 |
| NONOS SDK Version | `nonos-sdk 2.2.1+100 (190703)` | 標準 |
| SSL Support | `All SSL ciphers (most compatible)` | HTTPS を将来使う可能性を考慮 |
| Stack Protection | `Disabled` | ROM 使用量削減 |
| VTables | `Flash` | 標準 |
| Erase Flash | `Only Sketch` | フラッシュ全消去したい時のみ `All Flash Contents` |
| **CPU Frequency** | `80 MHz` | 標準。160MHz は消費電流増、電池運用では 80MHz 推奨 |

### 2.1 特に注意する 3 項目まとめ

| 項目 | 正解 | 誤選択時の症状 |
|---|---|---|
| **Reset Method** | `no dtr (aka ck)` | `dtr (aka nodemcu)` にすると書込み時に `Invalid head of packet (0x1C)` エラー (自動リセット回路が無いため) |
| **Flash Size** | `4MB (FS:2MB OTA:~1019KB)` | 1MB にすると書込みは成功するが SPIFFS/LittleFS 領域配置がズレて実行時異常 |
| **Flash Mode** | `DOUT (compatible)` | `DIO` にすると個体によっては起動しない (Serial モニタが Boot loop になる) |

---

## 3. 書き込み用の配線 (FTDI ↔ ESP-WROOM-02)

ユニバーサル基板上の恒久配線を前提。書込みの度に外す必要は無い。

### 3.1 恒久配線 (必ずやる)

| ピン | 接続先 | 抵抗 | 目的 |
|---|---|---|---|
| CH_PD (EN) | 3V3 | 10kΩ プルアップ | チップを有効化 |
| GPIO0 | 3V3 | 10kΩ プルアップ | 通常起動 (Flash boot) |
| GPIO2 | 3V3 | 10kΩ プルアップ | 起動ストラップ (High 必須) |
| GPIO15 | GND | 10kΩ プルダウン | 起動ストラップ (Low 必須) |
| GPIO16 (XPD_DCDC) | RST | 直結 | DeepSleep 復帰用 (電池運用時) |
| VCC | 3V3 | ─ | 電源 (HT7333-1 LDO 経由推奨) |
| GND | GND | ─ | ─ |

### 3.2 FTDI との接続 (書込み時のみ)

| FTDI 側 | ESP-WROOM-02 側 | 備考 |
|---|---|---|
| TX | RX (RXD, GPIO3) | クロス接続 |
| RX | TX (TXD, GPIO1) | クロス接続 |
| GND | GND | 共通グラウンド必須 |
| 3.3V | ─ | 電流不足の可能性大。基本は使わず、電池 or 外部 3.3V 電源から HT7333-1 経由で供給 |
| DTR/RTS | ─ | 生 ESP-WROOM-02 では使わない (Reset Method: no dtr のため) |

### 3.3 書込み時に手動で操作するスイッチ (任意、あると便利)

| スイッチ | 接続 | 動作 |
|---|---|---|
| RESET ボタン | RST ↔ GND (瞬間接続) | チップリセット |
| FLASH ボタン | GPIO0 ↔ GND (瞬間または保持) | フラッシュモード起動用 |

スイッチが無い場合はジャンパを一時的にワニ口クリップ等で GND に落とす方式でも可。

---

## 4. 書き込み手順 (毎回実行)

Reset Method: `no dtr (aka ck)` を選ぶ以上、書込みごとに **手動でフラッシュ
モードに入れる** 必要がある。手順は毎回同じ:

```
Step 1: 電源投入 (FTDI を PC 接続 or 電池 ON)

Step 2: GPIO0 を GND に接続 (FLASH ボタン押下 or ジャンパ)

Step 3: RESET ボタンを押して離す (RST を GND に一瞬落とす)
        → ESP はフラッシュ書込みモードで起動する
        → Serial モニタに何も表示されない静かな状態が正常

Step 4: GPIO0 を離す (通常時に戻す)
        → 一度手を離しても、既にフラッシュモードに入っているので OK

Step 5: Arduino IDE の右上「→」矢印ボタン (マイコンボードに書き込み) をクリック
        → コンパイル → 書込み進行を待つ
        → 100% になり "Hard resetting via RTS pin..." と出れば成功

Step 6: RESET ボタンを再度押して離す
        → 今度は通常起動 (GPIO0 が High なので Flash boot)
```

### 4.1 書き込み中に見る Arduino IDE の出力例

```
Executable segment sizes:
IROM   : 292352
IRAM   : 27520
DATA   :   1512
RODATA :   4936
BSS    :  27272
Sketch uses 326320 bytes (31%) of program storage space.
Global variables use 33720 bytes (41%) of dynamic memory.
esptool.py v3.0
Serial port COM11
Connecting....
Chip is ESP8266EX
Features: WiFi
Crystal is 26MHz
MAC: EC:FA:BC:XX:XX:XX
...
Writing at 0x00000000... (X %)
...
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
```

---

## 5. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `esptool.py error: Invalid head of packet (0x1C)` | Reset Method が `dtr (aka nodemcu)` になっている | `no dtr (aka ck)` に変更 |
| `Failed to connect to ESP8266: Timed out waiting for packet header` | GPIO0 が GND に落ちていない (フラッシュモード未進入) | §4 の手順を Step 2-3 からやり直す |
| `head packet error` | Flash Mode が個体と不整合 (DOUT/DIO) | `DOUT (compatible)` に変更 |
| `Chip erase completed` は成功するが起動しない | Flash Size が実チップと不一致 | `4MB (FS:2MB OTA:~1019KB)` に変更 |
| 書き込み後 Serial モニタで文字化けが続く | Boot 時のログ出力速度 (74880 bps) と Serial モニタの速度 (通常 115200) 不一致 | 文字化けは Boot 冒頭数行だけなので実害無し。詳細ログを見たいなら Serial モニタを 74880bps に切替え |
| `'D4' was not declared in this scope` (コンパイル時) | `Generic ESP8266 Module` ではピン別名記号 `D4` 等は未定義 | GPIO 番号を直接書く (例: `4`) |
| 書き込み中に電源が落ちる | FTDI の 3.3V 出力が電流不足 (最大 50mA 程度) | 別電源 (電池 + HT7333-1) から給電し、FTDI からは信号線のみ接続 |
| USB を認識しない | FTDI ドライバ未インストール | §1.3 参照 |
| 書き込み速度が遅い or 失敗頻発 | Upload Speed 460800 で信号品質不足 | 115200 に落として再試行 |

### 5.1 起動時の Serial ログ (74880bps) を確認したい場合

ESP8266 は Boot 時に 74880bps で内部ログを出す (通常 115200 でモニタしていると
文字化けする冒頭数行の正体)。詳細を確認したい場合は Arduino IDE の Serial モニタ
右下の速度を **74880 baud** に一時的に変更。以下のようなログが読める:

```
ets Jan  8 2013,rst cause:2, boot mode:(3,7)
load 0x40100000, len 3132, room 16
...
```

`rst cause` の意味:
- 1: Power on
- 2: External reset (RESET ボタン)
- 3: Software reset
- 4: Watchdog reset
- 5: DeepSleep wake

`boot mode` の意味:
- (1,x): Flash boot (通常起動、GPIO0=High)
- (3,x): UART download boot (書込みモード、GPIO0=Low)

---

## 6. 電池運用時の DeepSleep 動作確認

書込み完了直後は **FTDI から Serial モニタでログを見ながら動作確認** できる
(デバッグ版スケッチ `ESP8266_DeepSleep_FixedIP_Sensor_debug.ino` を使う)。

しかし本番用スケッチ (`ESP8266_DeepSleep_FixedIP_Sensor.ino`) は Serial 出力を
無効化しているので、動作確認は Pi 側の Flask ログで:

```bash
# Pi の SSH で
sudo journalctl -u temperature-server -f
```

30 秒 (or 設定値) 周期で `POST /api/temperature` が受信されれば OK。

詳細は `outputs/ESP8266_DeepSleep_FixedIP_Sensor_debug/` のデバッグ版を参照。

---

## 7. ESP-WROOM-02 の技適 (電波法) について

- **技適認証: R 201-160606**
- Espressif 純正モジュールの ESP-WROOM-02 は技適取得済で、日本国内で
  合法的に電波を出せる
- **秋月電子通商 AE-ESP-WROOM-02 DIP 化キット** は元モジュールに DIP 化基板を
  はんだ付けしただけで技適は維持される
- 生の ESP-12F/ESP-12S (Espressif 純正でない中華モジュール) は技適を取っていない
  可能性があるので日本国内では使わない
- 技適マークは モジュール表面のシルクで確認可能

## 8. 関連ドキュメント

- `outputs/ESP8266_BareModule_Wiring/ブレッドボード配線ガイド.md` — 開発時のブレッドボード配線
- `outputs/ESP8266_BareModule_Wiring/電池駆動配線ガイド.md` — 電池運用時の配線 (HT7333-1 LDO)
- `outputs/ESP8266_DeepSleep_FixedIP_Sensor/ESP8266_DeepSleep_FixedIP_Sensor.ino` — 本番用スケッチ
- `outputs/ESP8266_DeepSleep_FixedIP_Sensor_debug/` — Serial 出力有効のデバッグ版
- `outputs/docs/RaspberryPi_セットアップガイド.md` — Pi 側の統合手順
