# 🔰 初心者向け: WiFi 認証情報の設定ガイド

このプロジェクトは GitHub 公開のため、**WiFi の SSID・パスワードは意図的にプレースホルダにしてあります**。
実際に動かす前に、必ず自分の環境の値に書換えてください。

**このガイドの読み方:**
- Arduino IDE で `.ino` ファイルを開いたことがあれば OK
- コマンドラインは Raspberry Pi の SSH で最初の 2 コマンドだけ使います
- 所要時間: **15 分**

---

## 📋 全体像

このプロジェクトには 2 つの独立した WiFi 認証情報があります:

| # | 対象 | 場所 | 書換えるファイル数 |
|---|---|---|---|
| A | **Raspberry Pi 自作 AP の SSID/パスワード** (ESP センサーが接続する側) | Pi 側 `hostapd.conf` + 各 `.ino` + Flask の `.env` | 9 個 |
| B | **家/現場の既存 WiFi の SSID/パスワード** (Pi がインターネット側で使う) | Pi 側 `netplan/*.yaml` | 1 個 (現地ルーターに合わせる) |

**A と B は別物です**。混同しないよう表で色分け:

```
    [家の WiFi ルーター]  ← B: Pi の wlan0 がここに接続 (インターネット出口)
           │
           │ 家 WiFi (既に自宅に存在する WiFi ルーター)
           ▼
    [Raspberry Pi] ─────── wlan1 上に自作 AP 立てる (これが A)
           │
           │ YOUR_AP_SSID_HERE (自分で決めた SSID)
           ▼
    [ESP32 温度センサー]  ← A: ESP が RaspberryPi の AP に接続してデータ POST
```

---

## A. Raspberry Pi 自作 AP の SSID/パスワード設定 (9 か所)

### A-1. まず自分の AP 名とパスワードを 1 つ決める

以下の 2 つを紙にメモしてください。**あとで全部の場所に同じ値をコピペする**ので、
先に決めておく方が楽です:

- **SSID** (アクセスポイント名): 好きな名前 (例: `MySensorNet`、`FactoryTemp`)
  - 半角英数字とハイフン、アンダースコアが安全
  - 8-31 文字くらい
  - 現地展開する場合、他店舗と被らない工夫を
- **パスワード**: 8 文字以上 (WPA2 の下限)
  - 例: `MyStr0ngP@ss2026` みたいなランダムに近い文字列
  - Pi と ESP しか使わないので長くしても支障なし (物理接続じゃないので入力は 1 回だけ)

**⚠️ このパスワードが漏れると、同じネットワーク上に第三者が接続できてしまいます。**
`password123` みたいな安易な値は避けてください (現場の Wi-Fi デバイスが総当たり攻撃される)。

### A-2. Pi 側の hostapd 設定 (1 か所目)

**Pi bash** (SSH で入る):

```bash
sudo nano /etc/hostapd/hostapd.conf
```

以下の 2 行を **自分が決めた値** に書換え:

```conf
ssid=YOUR_AP_SSID_HERE          ← ここを "MySensorNet" 等に
wpa_passphrase=YOUR_AP_PASSWORD_HERE  ← ここを "MyStr0ngP@ss2026" 等に
```

保存 (`Ctrl+O` → `Enter` → `Ctrl+X`)、その後:

```bash
sudo systemctl restart hostapd
sudo systemctl status hostapd    # active (running) なら OK
```

### A-3. Flask の .env (1 か所目、実は .env は各自作る)

**Pi bash:**

```bash
cd /home/pi/temperature_server
cp .env.example .env             # 初回だけ
nano .env
```

以下 2 行を **A-2 と同じ値** に書換え:

```env
AP_SSID=YOUR_AP_SSID_HERE           ← 同じ値
AP_PASSWORD=YOUR_AP_PASSWORD_HERE   ← 同じ値
```

`SECRET_KEY` も書換え推奨 (下のコマンドで自動生成):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# → 出力された文字列を .env の SECRET_KEY= の後ろに貼付け
```

保存後 Flask 再起動:

```bash
sudo systemctl restart temperature-server
```

### A-4. ESP スケッチ (7 個、Windows PC の Arduino IDE で)

7 個のスケッチすべて同じ書換えです:

1. `ESP32C3_XIAO_DS18B20_WiFi/ESP32C3_XIAO_DS18B20_WiFi.ino`
2. `ESP32_DS18B20_WiFi/ESP32_DS18B20_WiFi.ino`
3. `ESP32_DS18B20_WiFi_Battery/ESP32_DS18B20_WiFi_Battery.ino`
4. `ESP8266_DeepSleep_FixedIP_Sensor/ESP8266_DeepSleep_FixedIP_Sensor.ino`
5. `ESP8266_DeepSleep_FixedIP_Sensor_debug/ESP8266_DeepSleep_FixedIP_Sensor_debug.ino`
6. `ESP8266_DeepSleep_FixedIP_Sensor_LED/ESP8266_DeepSleep_FixedIP_Sensor_LED.ino`
7. `ESP8266_DS18B20_HTTPPOST/ESP8266_DS18B20_HTTPPOST.ino` (ARCHIVE)

**手順** (どのスケッチも同じ):

1. Arduino IDE でファイルを開く
2. `Ctrl+H` で「置換」ダイアログ
3. 「検索」に `YOUR_AP_SSID_HERE`、「置換」に **A-2 で決めた SSID**
4. 「すべて置換」
5. 続いて「検索」に `YOUR_AP_PASSWORD_HERE`、「置換」に **A-2 で決めたパスワード**
6. 「すべて置換」
7. `Ctrl+S` で保存
8. ESP チップを USB 接続、「マイコンボードに書き込む」

**⚠️ 書換えた `.ino` は自分専用**。GitHub に push しないでください
(既に `.gitignore` で個別に除外していない場合は、書換え済スケッチを
別ディレクトリ (例: `~/my-configured-sketches/`) にコピーして使うと安全)。

---

## B. Pi が接続する家/現場 WiFi の設定 (1 か所)

Pi は wlan0 で家のルーターに接続してインターネットに出ます。この設定は
**Pi 単体で完結**、GitHub のコードとは無関係です。

**方法 1: Raspberry Pi Imager でイメージ書込み時に設定** (最初のセットアップ時)

- Imager の「OS カスタマイズ」→ WiFi タブで SSID/パスワード入力

**方法 2: 後から変更する** (Pi bash)

```bash
sudo nmtui              # 対話 UI で WiFi 設定
# または
sudo nano /etc/netplan/*.yaml
sudo netplan apply
```

**⚠️ Tailscale を導入済なら、家 WiFi が変わっても外から復旧可能**
(`docs/Tailscale_導入ガイド.md` 参照)。まだの人は Tailscale 入れる前に
本作業する場合、SSH 切れる可能性に注意 (物理コンソールで復旧できる状態で作業)。

---

## 🔍 動作確認チェックリスト

**A の設定 (Pi 自作 AP)** が正しく反映されたか:

- [ ] Pi bash で `sudo systemctl status hostapd` が `active (running)`
- [ ] スマホの WiFi 一覧に **A-2 で決めた SSID** が表示される
- [ ] スマホから **A-2 で決めたパスワード** で接続できる (接続後インターネット無しで OK)
- [ ] `sudo journalctl -u hostapd -n 20` にエラー無し
- [ ] ESP に書換え済スケッチを書込み、シリアルモニタで:
    ```
    Connecting to WiFi: MySensorNet (static, derived from MAC)
    WiFi connected: ip=192.168.4.XXX rssi=-XX dBm
    ※ IP は MAC から自動算出 (192.168.4.100〜227)。設定不要
    ```

**B の設定 (家 WiFi)** の確認:

- [ ] `ip -4 addr show wlan0` で IP が付いている (家ルーターの LAN 帯)
- [ ] `ping -c 2 8.8.8.8` が通る

---

## 🆘 よくあるトラブル

| 症状 | 原因 | 対処 |
|---|---|---|
| ESP のシリアルに `WL_NO_SSID_AVAIL` | SSID タイポ or hostapd 停止中 | 半角/全角、大文字/小文字を厳密に一致確認 |
| ESP のシリアルに `WL_CONNECT_FAILED` | パスワード違い | 認証情報を再確認、hostapd 側と ESP 側で同じか照合 |
| Pi の hostapd が起動しない | wlan1 (USB WiFi ドングル) 未接続 or ドライバ未導入 | `RaspberryPi_AP_Setup/` のガイド参照 |
| ESP が繋がるが POST が届かない | ESP の `serverURL` が `192.168.4.1` になっているか | 各 .ino の `const char* serverURL` 確認 |
| 「AP に接続はできるがネットは出ない」 | それが仕様 | Pi 自作 AP は隔離ネットワーク。ネット出口は Pi の wlan0 側 |

---

## 💡 補足: なぜプレースホルダにしているか

GitHub で世界公開する以上、**開発時のデフォルトパスワードをそのまま使う人が出る** ことを避けたいためです。

- `password123` みたいな公開デフォルトは、公開直後から周辺で総当たり攻撃を受けます
- 各自の環境で「一意なパスワードを 1 回考える」ことを強制する仕組み

センシティブな運用ネットワーク (顧客現場、業務用) では特に気をつけてください。

---

## 📚 関連ドキュメント

- `docs/RaspberryPi_セットアップガイド.md` — Pi 全体の初期構築
- `RaspberryPi_AP_Setup/Raspberry Pi DHCPAPセットアップガイド.md` — hostapd/dnsmasq 詳細
- `docs/デバイス識別設計.md` — MAC ベースの device_id 仕組み
- `docs/Tailscale_導入ガイド.md` — 遠隔 SSH の準備
