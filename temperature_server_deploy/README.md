# 方針 P: 既存 temperature_server を Pi に展開する手順 (Z: 起点版)

## 全体フロー

```
[I:] 既存実装 (稼働実績)
    ↓ (rsync で venv 等除外して統合コピー、既に完了)
[Z:] outputs/temperature_server_full/  ← ★公開ソース (GitHub 反映元)
    ↓ (Pi へ scp)
[Pi] /home/pi/temperature_server/
    ↓ (venv + systemd)
[Running]
```

**重要**: Pi へは **Z: から scp** します。I: は今後手を入れず、Z: が唯一の source of truth。

## 前提

- Pi ホスト: `takemetothehospital`、IP: `192.168.11.200`
- Pi ユーザー名: `pi` (プロンプト `pi@takemetothehospital:~ $` の左側が username)
- 展開先: `/home/pi/temperature_server/`
- Z: 側のソース: `Z:\afterNK\ESPSARVER\outputs\temperature_server_full\`
- 現行 (私が最初に作った) 実装は退避
- DB は完全破棄 (新規スタート)
- ESP スケッチは変更不要 (既存 `/api/temperature` が互換)

---

## Phase 1: 現行実装を停止・退避

### 【Pi の SSH セッション で実行】

Pi に入る: `ssh pi@192.168.11.200`

```bash
sudo systemctl stop temperature-server
sudo systemctl disable temperature-server
sudo mv /etc/systemd/system/temperature-server.service /etc/systemd/system/temperature-server.service.old

mv ~/temperature_server ~/temperature_server_old_20260716

sudo systemctl status temperature-server 2>&1 | head -5
curl http://localhost:5000/health 2>&1 | head -3
```

完了したら `exit` で SSH を抜ける。

---

## Phase 2: Z: から Pi へフル転送

### 【Windows PowerShell で実行】

```powershell
cd Z:\afterNK\ESPSARVER\outputs\temperature_server_full
scp -r . pi@192.168.11.200:/home/pi/temperature_server/
```

上記コマンドで `temperature_server_full/` の中身全部が Pi の `/home/pi/temperature_server/` に転送される (systemd unit や .env も同梱)。

**もし転送先ディレクトリが既に存在するエラーが出たら:**

Phase 1 で `~/temperature_server` を退避済みのはずなので発生しないはずだが、念のため:

```powershell
ssh pi@192.168.11.200 "ls /home/pi/temperature_server 2>&1"
```

これで `No such file or directory` が出れば大丈夫。存在してしまっている場合は Phase 1 の退避コマンドを再実行してから Phase 2 に戻る。

---

## Phase 3: Pi 側セットアップ

### 【PowerShell で SSH】

```powershell
ssh pi@192.168.11.200
```

### 【Pi の SSH セッション で実行】

```bash
cd ~/temperature_server

# venv 新規作成 (Z: 側にはそもそも venv を含めていない)
python3 -m venv venv
source venv/bin/activate

# 依存インストール
pip install --upgrade pip
pip install -r requirements.txt
```

**もし selenium で失敗したら (Chromium 依存で失敗しやすい):**

```bash
sed -i '/selenium/d' requirements.txt
pip install -r requirements.txt
```

**続けて:**

```bash
# .env が反映されているか確認 (Phase 2 で同梱転送済)
cat .env | head -10

# データ・ログディレクトリ作成
mkdir -p data logs

# systemd unit を反映 (Phase 2 で同梱転送済)
sudo cp systemd/temperature-server.service /etc/systemd/system/temperature-server.service
sudo systemctl daemon-reload
sudo systemctl enable temperature-server

# サービス起動
sudo systemctl start temperature-server
sleep 2
sudo systemctl status temperature-server --no-pager -l
```

`Active: active (running)` になれば OK。

---

## Phase 4: 動作確認

### 【Pi で実行】

```bash
curl http://localhost:5000/api/status

curl -X POST http://localhost:5000/api/temperature \
    -H "Content-Type: application/json" \
    -d '{"device_id":"test-curl","temperature":25.5,"name":"test-sensor"}'

sudo journalctl -u temperature-server -f
```

### 【ブラウザで確認】

- `http://192.168.11.200:5000/` — 新ダッシュボード
- `http://192.168.11.200:5000/management` — 管理画面
- `http://192.168.11.200:5000/api/routes` — 全 API エンドポイント一覧

30 秒周期の ESP POST が続いていれば、`ESP8266_ip208_30sec` / `DS18B20-ESP8266-208` が表示されるはず。

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `systemctl start` で失敗 | Python 依存不足 | `sudo journalctl -u temperature-server -n 30` で `ModuleNotFoundError` 特定 → 該当 pkg を pip install |
| POST しても保存されない | DB 未初期化 | `ls -la data/temperature.db` で存在確認 |
| ダッシュボード真っ白 | template not found | template_folder のパスを確認 |
| `/video_feed` で 500 | opencv (cv2) 未 install | 使わないので放置で OK |
| `/wifi/xxx` で 500 | wifi_manager 初期化失敗 | 使わないなら放置で OK |

---

## 撤退プラン

### 【Pi で実行】

```bash
sudo systemctl stop temperature-server
sudo systemctl disable temperature-server
mv ~/temperature_server ~/temperature_server_new_20260716
mv ~/temperature_server_old_20260716 ~/temperature_server
sudo mv /etc/systemd/system/temperature-server.service /etc/systemd/system/temperature-server.service.new
sudo mv /etc/systemd/system/temperature-server.service.old /etc/systemd/system/temperature-server.service
sudo systemctl daemon-reload
sudo systemctl enable temperature-server
sudo systemctl start temperature-server
```

---

## Z: 内の最終構造 (公開想定)

```
Z:\afterNK\ESPSARVER\outputs\
├── ESP8266_DeepSleep_FixedIP_Sensor\           ← ESP スケッチ (静的IP版・主流)
│   └── ESP8266_DeepSleep_FixedIP_Sensor.ino
├── ESP8266_DeepSleep_FixedIP_Sensor_debug\     ← ESP スケッチ (Serial 出力有効・デバッグ用)
│   └── ESP8266_DeepSleep_FixedIP_Sensor_debug.ino
├── temperature_server_full\                    ← Pi 側 Flask (既存実装ベース・公開ソース)
│   ├── app/, database/, services/, templates/, utils/
│   ├── systemd/temperature-server.service      ← pi ユーザー版
│   ├── .env                                     ← Pi 用環境変数 (.gitignore 対象)
│   ├── .env.example                             ← 公開用テンプレート
│   ├── docs/                                    ← 既存の設計書 12 本
│   └── ... (config.py, run.py, requirements.txt 等)
├── temperature_server_deploy\                  ← デプロイ手順書 (本 README)
│   └── README.md
├── temperature_server\                          ← ★私が最初に作った実装 (廃止済・削除候補)
├── ESP8266_DS18B20_HTTPPOST\                    ← ★私の STEP 2 実装 (廃止済・削除候補)
├── RaspberryPi_AP_Setup\                        ← AP セットアップガイド
└── ESP8266_BareModule_Wiring\                   ← 配線ガイド
```

★ の 2 つは方針 A/P 切替で不要になったフォルダ。今後の整理で削除可能。
