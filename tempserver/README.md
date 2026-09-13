# tempserver — 連載版の温度サーバー

ブログ連載「しまい込んでいた電子部品と、AI で形にできる温度監視システム」の
第8回・第9回で作ったものです。**1 ファイル 333 行**の Flask サーバーで、

- ESP8266 / ESP32 から届く **HTTP POST**
- ESP-NOW の Master から届く **USB シリアル**

の 2 経路を 1 か所で受けて、SQLite に貯め、ブラウザに表示します。

リポジトリの `temperature_server*` は別系統（過去の実装）です。
**連載を追って作るのはこの `tempserver/` です。**

---

## 中身

| ファイル | 役割 |
|---|---|
| `app.py` | サーバー本体。受信・保存・API・掃除まで全部これ 1 本 |
| `templates/index.html` | ダッシュボード（一覧表と Chart.js のグラフ） |
| `templates/manage.html` | 表示名（ニックネーム）の管理画面 |
| `static/vendor/` | Chart.js と日付アダプタの実体。CDN を使わないためリポジトリに同梱 |
| `tempserver.service` | systemd のユニット。電源投入で勝手に上がる |
| `.env.example` | 設定の雛形。`.env` にコピーして使う |
| `requirements.txt` | 依存の記録。実際の導入は下記の apt を推奨 |

データベース `temperature.db` は初回起動時に自動で作られます。
リポジトリには入っていません。

---

## 動作を確認した環境

- Raspberry Pi 4B / Raspberry Pi OS
- Python 3.13.5、Flask 3.1.1、pyserial（apt 版）
- ブラウザは、同じ LAN 内の PC / スマートフォン、および **Pi の AP に直接繋いだ端末**

### JavaScript は CDN から読みません

Chart.js と日付アダプタは `static/vendor/` に実体を置いてあり、
`templates/index.html` はそこを見ています。**インターネットは一切要りません。**

もともとは CDN (`cdn.jsdelivr.net`) から読んでいましたが、やめました。
現場に置いた Pi の AP には**外に出る道がありません**。その AP にノート PC を繋いで
ダッシュボードを開くと、表は出るのに**グラフだけ出ず、しかも表示がひどく遅い**という
状態になります。ブラウザが届かない CDN の名前解決を待ってから先へ進むためです
(`ERR_NAME_NOT_RESOLVED`)。

同梱しているのは次の 3 つです。いずれも配布元の最小化済みファイルそのままで、
ライセンス表記もファイル先頭に残してあります。

| ファイル | 出どころ |
|---|---|
| `chart.umd.min.js` | Chart.js 4.4.0 (MIT) |
| `date-fns.min.js` | date-fns 3.6.0 (MIT) |
| `chartjs-adapter-date-fns.bundle.min.js` | chartjs-adapter-date-fns 3.0.0 (MIT) |

更新したいときは、同じ URL から取り直して同名で置き換えてください。

```bash
cd ~/tempserver/static/vendor
curl -fsSL -o chart.umd.min.js https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js
curl -fsSL -o date-fns.min.js https://cdn.jsdelivr.net/npm/date-fns@3.6.0/cdn.min.js
curl -fsSL -o chartjs-adapter-date-fns.bundle.min.js https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js
```

---

## 導入

### 1. 必要なものを入れる

```bash
sudo apt update
sudo apt install -y python3-flask python3-serial sqlite3
```

venv は使いません。apt 版は OS が管理する Python にそのまま入るので、
`pip` の `externally-managed-environment` エラーを踏みません。

### 2. 取ってくる

```bash
cd ~
git clone https://github.com/whiskerpad/sensorserverwithESP.git
mkdir -p ~/tempserver
cp -r ~/sensorserverwithESP/tempserver/. ~/tempserver/
cd ~/tempserver
ls
```

`app.py` と `templates/` が見えれば成功です。

> `tempserver.service` の中身が `/home/pi/tempserver` を指しているので、
> **置き場所は `~/tempserver` に合わせてください。**
> ユーザー名が `pi` 以外の場合は、次の 3 か所を自分の名前に書き換えます。
> `User=` / `WorkingDirectory=` / `ExecStart=`

### 3. 設定（省略可）

```bash
cd ~/tempserver
cp .env.example .env
nano .env
```

既定のままで動きます。保持日数を変えたいとき、あるいは
シリアル変換基板を複数挿していて Master を名指ししたいときだけ編集してください。

**注意:** `app.py` は python-dotenv を使っていません。`.env` を読むのは
systemd の `EnvironmentFile=` だけです。手で `python3 app.py` と起動した場合、
`.env` は無視されて既定値で動きます。

### 4. まず手で動かしてみる

```bash
cd ~/tempserver
python3 app.py
```

`Running on http://0.0.0.0:5000` が出たら、**別の端末**から叩きます。

```bash
curl -X POST http://localhost:5000/api/temperature \
  -H "Content-Type: application/json" \
  -d '{"device_id":"TEST-0001","temperature":25.0,"voltage":4.1}'
```

`{"status":"ok"}` が返り、`app.py` を動かしている側に
`[wifi] TEST-0001  25.00℃ ...` と出れば、受信から保存まで通っています。

入ったことを直接確かめる場合:

```bash
sqlite3 ~/tempserver/temperature.db \
  "SELECT * FROM temperatures WHERE device_id='TEST-0001';"
```

確認できたら試験データは消しておきます。

```bash
sqlite3 ~/tempserver/temperature.db \
  "DELETE FROM temperatures WHERE device_id='TEST-0001';"
```

`Ctrl+C` で `app.py` を止めます。

### 5. 自動起動にする

```bash
sudo cp ~/tempserver/tempserver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tempserver
```

状態を見ます。

```bash
systemctl is-active tempserver
journalctl -u tempserver -n 30 --no-pager
```

`active` と出て、ログに `[serial] ... を開きました` あるいは
`[serial] シリアルポートが見つかりません` が出ていれば動いています。
後者は Master を挿していないだけで、異常ではありません。

### 6. 開く

```
http://<Pi の IP アドレス>:5000/
```

表示名の編集は `http://<Pi の IP アドレス>:5000/manage` です。

開き方は 3 通りあります。**`localhost` が使えるのは Pi 本体の中だけ**である点に注意してください。

| どこから | アドレス |
|---|---|
| Pi 本体（モニタとキーボードを付けて） | `http://localhost:5000/` |
| 同じ LAN の PC / スマートフォン | `http://<Pi の IP アドレス>:5000/` |
| Pi の AP に直接繋いだ端末 | `http://192.168.4.1:5000/` |

3 番目は、インターネットが無い現場でそのまま使えます。AP に繋いだ端末で
`http://localhost:5000/` と打つと、**その端末自身**の 5000 番を探しに行くだけなので
必ず失敗します。

---

## 送る側

このリポジトリの以下が対応します。詳しくは連載本文を参照してください。

| ディレクトリ | 経路 |
|---|---|
| `ESP8266_DeepSleep_FixedIP_Sensor/` | HTTP POST（WiFi 子機、DeepSleep） |
| `ESP8266_ESPNOW_Sensor/` `ESP32C3_ESPNOW_Battery_Sensor/` | ESP-NOW 子機 |
| `ESP32_ESPNOW_Master/` | ESP-NOW の受信役。USB で Pi に挿す |

スケッチ内の SSID / パスワードはプレースホルダになっています。
自分の環境の値に書き換えてから書き込んでください。

---

## API

| メソッド | パス | 用途 |
|---|---|---|
| `POST` | `/api/temperature` | 子機からの受信口 |
| `GET` | `/api/latest` | デバイスごとの最新 1 件 |
| `GET` | `/api/history?hours=24` | 直近 N 時間の履歴（1〜720） |
| `GET` | `/api/nicknames` | 表示名の一覧 |
| `PUT` | `/api/nicknames/<device_id>` | 表示名の設定（無ければ追加） |
| `DELETE` | `/api/nicknames/<device_id>` | 表示名の削除（温度データは残る） |
| `GET` | `/` | ダッシュボード |
| `GET` | `/manage` | 表示名の管理画面 |

`device_id` の接頭辞で種類を見分けています。

- `MST-` … ESP-NOW の Master
- `ESP-` … WiFi 子機
- `NOW-` … ESP-NOW 子機

---

## 詰まったとき

| 症状 | 見るところ |
|---|---|
| `systemctl status` が `failed` | `journalctl -u tempserver -n 50 --no-pager` に Python の例外が出ている |
| ブラウザは開くが表が空 | まだ 1 件も届いていない。上の `curl` で試験データを入れて切り分ける |
| 表は出るがグラフが出ない | `static/vendor/` の 3 ファイルが欠けている。`curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5000/static/vendor/chart.umd.min.js` が 200 か見る |
| `[serial] シリアルポートが見つかりません` が続く | Master が挿さっていない、または `ls /dev/ttyUSB* /dev/ttyACM*` に出ない |
| `[serial] 解釈できない JSON` | Master 側のファームウェアが古い。連載の Master スケッチに更新する |
| `.env` を変えたのに効かない | 手で `python3 app.py` していないか。systemd 経由で再起動する |
| AP に繋いだ端末から開けない | `localhost` と打っていないか。`http://192.168.4.1:5000/` を打つ |
| ポート 5000 が塞がっている | `sudo ss -tlnp \| grep 5000` で犯人を見る |

---

## ライセンス

リポジトリのルート `LICENSE` に従います。
