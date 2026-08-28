# ESP-NOW 統合ガイド

WiFi インフラ (AP + IP + HTTP) を介さずに、ESP32/ESP32-C3 同士が直接
無線通信する仕組み「ESP-NOW」を本プロジェクトで使う方法。

## ESP-NOW と WiFi 直接 POST の違い

| 項目 | WiFi 直接 POST | ESP-NOW |
|---|---|---|
| **接続時間 (電源投入から送信まで)** | 2〜10 秒 (WiFi 認証 + DHCP or 固定 IP) | ~100 ms (ペアリング済みなら送信のみ) |
| **DeepSleep との相性** | 起動毎に WiFi 接続で ~2秒消費 | 起動毎に ~100ms、電池寿命 5〜10 倍延長可能 |
| **プロトコル** | TCP/IP、HTTP | 独自の 802.11 拡張 (Layer 2) |
| **ペア設定** | 不要 (SSID/pass だけ) | 事前に MAC アドレス登録が必要 |
| **中継の必要性** | 不要 (AP に直接) | Master (受信/中継役) が必要 |
| **可視化** | Flask がそのまま受信 | Master が Serial 経由で Pi に転送 |
| **技適** | 生 ESP モジュールは要確認 | 同上 |

**採用判断の目安**:
- 常時給電 or 30 秒以下の頻繁送信 → **WiFi 直接 POST**
- 電池運用 + 分単位以上のインターバル → **ESP-NOW**
- 混在も可能 (ESP-WROOM-02 で WiFi、ESP32-C3 で ESP-NOW)

---

## システム構成

```
[ESP32-C3 sensor 1] ─┐
[ESP32-C3 sensor 2] ─┼── ESP-NOW ──→ [ESP32 Master] ─── USB Serial ──→ [Raspberry Pi]
[ESP32   sensor 3] ─┘                                                       │
                                                                            ▼
                                                              Flask + SQLite + Dashboard
```

Master は WiFi AP (192.168.4.1) との接続を要さず、ESP-NOW 受信専用で動作。
Pi との接続は USB シリアル。Pi 側の `services/serial_reader.py` が Serial 経由で
受け取って `/api/temperature` に転送する (SERIAL_ENABLED=True にする必要あり)。

---

## 必要なスケッチ (Z: 内)

| フォルダ | チップ | 役割 |
|---|---|---|
| `ESP_MAC_Address_Getter/` | 各チップ (書込み後 Serial モニタで MAC 表示) | セットアップ用 |
| `ESP32_ESPNOW_Master/` | ESP32 (WROOM-DA 等) | ESP-NOW 受信 + Serial 出力 |
| `ESP32_ESPNOW_Sensor/` | ESP32 | センサー (常時給電・DeepSleep なし) |
| `ESP32C3_ESPNOW_Battery_Sensor/` | ESP32-C3 | センサー (電池 + DeepSleep 対応) |

---

## セットアップ手順 (4 ステップ)

### Step 1: Master 用 ESP32 の MAC アドレス取得

Master にする ESP32 に `ESP_MAC_Address_Getter/ESP_MAC_Address_Getter.ino` を
書き込み、Arduino IDE の Serial モニタ (115200 bps) で MAC を確認:

```
=== ESP32 MAC Address Getter ===
MAC Address: 2C:BC:BB:4D:99:BC
```

この 6 バイトをメモ (例: `2C, BC, BB, 4D, 99, BC`)。

### Step 2: 各センサーに Master MAC を埋め込む

センサースケッチ (`ESP32_ESPNOW_Sensor/` や `ESP32C3_ESPNOW_Battery_Sensor/`)
の `masterMAC[]` を Step 1 で取得した値に書き換え:

```cpp
// マスター ESP32 の MAC アドレス
uint8_t masterMAC[] = {0x2C, 0xBC, 0xBB, 0x4D, 0x99, 0xBC};
```

同時に `SENSOR_ID` と `SENSOR_NAME` をチップごとに変える (例:
`"NOW_BAT_01"`, `"NOW_BAT_02"` など)。

### Step 3: 書き込み

- Master ESP32 → `ESP32_ESPNOW_Master/ESP32_ESPNOW_Master.ino`
- 各センサー → 該当スケッチ

Arduino IDE のボード設定は各チップ別に必要:
- ESP32 (WROOM-DA 等) → `ESP32 Dev Module`
- ESP32-C3 → `ESP32C3 Dev Module`

### Step 4: Master を Pi に USB 接続

Master ESP32 の USB を Pi の USB ポートに接続。Pi 側で:

```bash
# 認識確認
ls -la /dev/ttyUSB* /dev/ttyACM*

# 例: /dev/ttyUSB0 で認識される

# Flask の .env で Serial 有効化
sed -i 's/SERIAL_ENABLED=False/SERIAL_ENABLED=True/' ~/temperature_server/.env
sudo systemctl restart temperature-server

# 受信ログ確認
sudo journalctl -u temperature-server -f
```

各センサーからのデータが Master 経由で Pi に転送され、`temperatures` テーブルに
挿入されるはず。

---

## MAC アドレス管理のベストプラクティス

複数センサー運用時は MAC アドレスの管理が重要:

- 各チップに **物理的にラベルを貼る** (例: `ESP32C3 #01 MAC:XX:XX:XX:XX:XX:XX`)
- センサースケッチのコメントに **自分の MAC も併記**:
  ```cpp
  // Sensor ID: NOW_BAT_01
  // This chip's MAC: 84:CC:A8:XX:XX:YY
  // Master's MAC:    2C:BC:BB:4D:99:BC (masterMAC[])
  ```
- Master 側は逆に **どのセンサーからの受信か** を Serial ログに出す設計 (すでに実装済)

詳細は `ESPNOW_MAC_ADDRESS_GUIDE.md` (元プロジェクトから継承したガイド) を参照。

---

## 電池駆動 ESP32-C3 版の特徴

`ESP32C3_ESPNOW_Battery_Sensor/` の設計思想:

- DeepSleep 5 分間隔 (`SEND_INTERVAL 300` 秒) で電池寿命を最大化
- 起動 → 温度取得 → ESP-NOW 送信 → DeepSleep の一連が ~150ms 程度で完了
- GPIO ストラップの制約に配慮 (GPIO2/A0 を避けて GPIO3/A1 を使う)
- 電源監視は本 ADC で電池電圧を測定

### DS18B20 信号ピン (2026-08-16 統一 = GPIO4)

WiFi 版 (`ESP32C3_XIAO_DS18B20_WiFi`) と ESP-NOW 版
(`ESP32C3_ESPNOW_Battery_Sensor`) は、以前 DS18B20 の DATA ピンが異なっていた
(WiFi 版のコメントに "GPIO0 = D0" と書かれていたが、これは事実誤認。ESP-NOW 版は
GPIO4 で稼働実績あり)。

**XIAO ESP32-C3 のピン割当てで重要な事実**:

- **GPIO0 は物理ピンとして引き出されていない** (ESP32-C3 のストラッピングピンで内部使用)
- 基板ラベル **D0 は GPIO2** (GPIO0 ではない)
- **D2 は GPIO4** (実際に使えるピン)

Seeed Studio 公式ピンマップ参照:

| 基板ラベル | 実 GPIO 番号 |
|---|---|
| D0 | GPIO2 |
| D1 | GPIO3 |
| **D2** | **GPIO4** ← DS18B20 で使用 |
| D3 | GPIO5 |
| D4 | GPIO6 |
| ... | ... |

**2026-08-16: 両方 GPIO4 に統一** (以下の理由):

1. XIAO ESP32-C3 で GPIO0 は使えない (未引出し)
2. **GPIO4 は無印 ESP32、ESP32 WROOM-DA、ESP32-C3 系すべてで自由に使えるピン** (ストラッピング制約なし)
3. スケッチ間の一貫性

**既存ボードで GPIO4 に配線されているものはそのまま使えます。再配線不要。**
以前私が「GPIO4 → GPIO0 に移設」と書いた記述は誤りで撤回します
(XIAO ESP32-C3 で GPIO0 に配線しようとしても物理的にできない)。

**新規子機ボードを作る場合**:
- DS18B20 DATA → **D2 (= GPIO4)** ピン
- DS18B20 VCC → 3V3
- DS18B20 GND → GND
- DATA と 3V3 の間に 4.7kΩ プルアップ抵抗

### 測定周期の変更方法

各スケッチで定数を書換えるだけで周期を変えられます。**単位がスケッチごとに違うので注意**:

| スケッチ | 定数名 | 単位 | 現行値 | 5 分にするなら |
|---|---|---|---|---|
| `ESP32_DS18B20_WiFi_Battery` | `MEASURE_INTERVAL` + `SLEEP_DURATION_US` | ms + μs | 60000 / 60000000ULL | **300000 / 300000000ULL** |
| `ESP32C3_XIAO_DS18B20_WiFi` | `SEND_INTERVAL` | 秒 | 60 | **300** |
| `ESP32C3_ESPNOW_Battery_Sensor` | `SEND_INTERVAL` | 秒 | 300 (既に 5 分) | 変更不要 |
| `ESP8266_DeepSleep_FixedIP_Sensor` 系 | `DEEP_SLEEP_INTERVAL` | マイクロ秒 (μs、`e6` 表記) | 120e6 (2 分) | **300e6** |

**単位換算チート表**:

| 周期 | 秒 | ミリ秒 (ms) | マイクロ秒 (μs / e6 表記) |
|---|---|---|---|
| 30 秒 | 30 | 30000 | 30000000ULL / 30e6 |
| 1 分 | 60 | 60000 | 60000000ULL / 60e6 |
| 5 分 | 300 | 300000 | 300000000ULL / 300e6 |
| 10 分 | 600 | 600000 | 600000000ULL / 600e6 |
| 30 分 | 1800 | 1800000 | 1800000000ULL / 1800e6 |
| 1 時間 | 3600 | 3600000 | 3600000000ULL / 3600e6 |

**注意**:

- `ULL` サフィックスは 64bit 整数指定。60 秒 (60,000,000) までは 32bit で収まるが、それを超える値を書く際は必須 (無いと 71 分でオーバーフローする)
- ESP8266 の DeepSleep 最大は **約 71 分 (4294e6 μs)**。それ以上の周期にしたい場合は分割 sleep が必要
- 短周期 (30 秒未満) は WiFi 接続 + POST に 3-5 秒かかるので実用上非推奨。電池も食う
- ESP-NOW 版は通信が 0.2 秒 + 温度取得 1 秒程度なので、30 秒周期でも WiFi 版よりずっと電池持ちが良い

各スケッチの該当定数の直前にも同じ主旨のコメントを 2026-08-16 に追記済みです (書換え時にファイルを開けばすぐ参照可能)。

---

**参考消費電力 (ESP-NOW vs WiFi 直接 POST)**:

| モード | 起動〜送信完了時間 | 平均電流 (5 分間隔) |
|---|---|---|
| WiFi 直接 POST | 2〜3 秒 | ~0.5 mA (電池 3 本で数ヶ月) |
| ESP-NOW | 0.1〜0.3 秒 | ~0.05 mA (電池 3 本で 1 年以上) |

---

## Pi 側 Serial 受信の仕組み

`temperature_server_full/services/serial_reader.py` が担う。
`SERIAL_ENABLED=True` にすると起動時に:

1. USB シリアル (/dev/ttyUSB0 or /dev/ttyACM0) を自動検出
2. ESP32 Master からのシリアル出力を行単位で解釈
3. JSON フォーマットの行を検出したら内部で `/api/temperature` にリレー

Master ESP32 の Serial 出力フォーマット (JSON 1 行 / 送信):
```
{"sensor_id":"NOW_BAT_01","sensor_name":"DS18-NOW-Bat01","temp":24.5,"rssi":-45}
```

これを Flask 側の `sensor_id` フィールドと一致させれば、ダッシュボード表示
までシームレスに反映される。

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| センサー起動しても Master が受信しない | Master MAC 設定間違い | Step 1 の MAC を再確認、Step 2 で正しく埋め込み |
| **Master を別 ESP32 チップに交換した後、既存子機からデータが来なくなった** | **★ 子機の `masterMAC[]` が旧 Master の MAC のまま。ESP-NOW は宛先 MAC で送るので、新 Master には届かない** | **後述「Master 交換時の子機書換え」参照** |
| Master の Serial に受信ログが出ない | センサー電源 or WiFi 初期化不良 | センサーの Serial 出力 (デバッグモード) を確認 |
| Pi に届かない | SERIAL_ENABLED=False or USB 未認識 | `.env` 確認、`ls /dev/ttyUSB*` 確認 |
| 特定センサーだけ受信できない | チャンネル不一致 or WiFi.mode 未設定 | センサー側 `WiFi.mode(WIFI_STA)` + `WiFi.disconnect()` 確認 |
| DeepSleep から復帰しない | GPIO 配線不良 (ESP32-C3 は自動復帰) | ESP32-C3 は RTC タイマ復帰のみ、追加配線不要 |
| Master 起動時に `MST-XXXXXX` がダッシュボードに現れない | serial_reader が /dev/ttyUSB0 or ttyUSB1 を掴めていない、または screen が port を占有 | `sudo lsof /dev/ttyUSB*` で犯人特定、Flask 再起動 |

### ★ Master 交換時の子機書換え (陥りやすい罠)

**症状**:
- Master ESP32 を壊した/新品に差し替えた
- 差し替え後、子機からのデータがダッシュボードに出なくなった
- 子機自体は他の ESP に載せ替えると温度が読める → **子機ハードウェア・DS18B20 は正常**
- Master のシリアルモニタに `[ESP-NOW] Received from ...` が **一切出ない**

**原因**:

ESP-NOW は「宛先 MAC アドレス」で通信します。子機スケッチ内の
`uint8_t masterMAC[] = {0x??, 0x??, ...};` は **旧 Master チップの MAC を指し続けている** ため、
子機は毎回旧 MAC 宛に送信 → 該当チップがネットワーク上に存在せず ACK 無し → データロスト。
新 Master には物理的に電波が届いていても、宛先が違うので受信コールバックが発火しません。

**対処 (ダッシュボードから 3 クリックで完了)**:

1. ブラウザで `http://<Pi の LAN IP>:5000/` (または Tailscale 経由の `http://<hostname>:5000/`)
2. 上部 **📡 ESP-NOW Master 機** カードを `▶ 展開` でオープン
3. 新 Master の **C 配列** 行 (例: `{0xCC, 0xDB, 0xA7, 0x2F, 0x98, 0xBC}`) 右横の `📋 コピー` ボタン
4. Arduino IDE で以下いずれかのスケッチを開く:
   - `ESP32_ESPNOW_Sensor/ESP32_ESPNOW_Sensor.ino` (常時給電センサー)
   - `ESP32C3_ESPNOW_Battery_Sensor/ESP32C3_ESPNOW_Battery_Sensor.ino` (電池版)
5. `uint8_t masterMAC[] = {...};` の行を貼付けで置換
6. 該当子機に書込み (**複数センサーあれば全部**)

書込み後、次の送信周期 (常時給電は 30 秒、電池版は 300 秒) で Master シリアルモニタに
`[ESP-NOW] Received from XX:XX:XX RSSI=-XX` が出ればリカバリ成功。

**予防策**:

- Master を予備機と入れ替える場合は、事前に予備機の MAC を控えておく
- 子機がすでに現地展開されている場合、書換えは基本的に現場行きで USB 接続が必要になるので、
  Master 交換は「予備機の MAC を旧 Master と同じにできない」と割り切って、
  可能な限り Master チップは長寿命部品を選ぶ (温度環境も含めて劣化対策)
- LiPo バッテリー切れやリセットで Master が短時間ダウンしても、Master の MAC は
  ハード固有で変わらない → 復帰後は子機側変更不要 (原因はここではない)

**なぜ Pi の LAN IP や Tailscale IP が変わっても平気で、Master MAC 交換だけ問題になるのか**:

- Pi 側の Flask には ESP-NOW 子機は直接接続していない (WiFi 直接 POST 系だけ Pi に対して通信)
- ESP-NOW 子機 → Master → Serial → Pi の経路で、**Pi 側 IP は子機からは見えない**
- 子機が知っている唯一の宛先は「Master の MAC」だけ
- したがって Master 物理チップの識別=MAC が唯一のシングルポイント

---

## 関連ドキュメント

- `outputs/README.md` — システム全体概要
- `outputs/docs/Arduino_IDE_設定ガイド.md` — 生 ESP チップ書込み設定
- `outputs/docs/RaspberryPi_セットアップガイド.md` — Pi 全体の構築手順
- `outputs/docs/ESPNOW_MAC_ADDRESS_GUIDE.md` — MAC アドレス取得の詳細
- `outputs/temperature_server_full/docs/esp_devices/ESP32_CODE.md` — ESP32 コード解説
- `outputs/temperature_server_full/docs/esp_devices/ESP_NOW_DS18B20.md` — DS18B20 との組み合わせ
- `outputs/temperature_server_full/docs/esp_devices/ESP_NOW_IMPLEMENTATION.md` — 実装詳細
- `outputs/temperature_server_full/docs/esp_devices/ESP32_SERIAL_GATEWAY.md` — Serial ゲートウェイ設計
