# 🚀 完全セットアップガイド

**初心者向け：0 からのセットアップを手順通りに実行してください**

---

## セットアップ前の確認

### 必要なハードウェア

- ✅ Raspberry Pi 4 (2GB RAM 以上)
- ✅ Micro SD カード (16GB 以上)
- ✅ USB WiFi ドングル：TP-Link Archer T2U Plus
- ✅ ESP32 マイコンボード（DS18B20 温度センサー搭載）
- ✅ HDMI ケーブル + モニター（または SSH アクセス）
- ✅ USB 電源アダプタ

### 前提知識

- Linux/Bash コマンドの基本知識
- Python の基本理解
- WiFi ネットワークの基本知識

---

## Phase 1: Raspberry Pi OS インストール

### 1.1 SD カード準備

```bash
# Windows/Mac で Raspberry Pi Imager をダウンロード
# https://www.raspberrypi.com/software/

# または Linux で:
sudo apt-get install rpi-imager
rpi-imager

# 以下の設定でイメージを書き込み：
# - OS: Raspberry Pi OS (64-bit) - Debian 13
# - ストレージ: Micro SD カード
# - 詳細設定:
#   - ホスト名: raspberrypi
#   - SSH 有効化: はい
#   - ユーザー名: raspberry
#   - パスワード: [任意のパスワード]
#   - WiFi SSID: [接続する WiFi 名]
#   - WiFi パスワード: [WiFi パスワード]
```

### 1.2 初期起動

```bash
# Raspberry Pi に SD カードを挿して電源投入
# 1 分待ってから...

# SSH で接続
ssh pi@raspberrypi.local
# または
ssh pi@192.168.11.200

# パスワード入力（初期設定時のパスワード）
```

### 1.3 システムアップデート

```bash
ssh pi@raspberrypi.local << 'EOF'
  # パスワード入力時は対話的に接続するか、キーベース認証を設定
  
  # システムアップデート
  sudo apt-get update
  sudo apt-get upgrade -y
  
  # 必要なツールをインストール
  sudo apt-get install -y \
    build-essential \
    dkms \
    git \
    curl \
    wget \
    python3-pip \
    python3-venv
EOF
```

---

## Phase 2: USB WiFi ドングル設定

[WIFI_SETUP.md](WIFI_SETUP.md) の **Step 1 ~ 3** を実行してください。

主な作業：
1. ドライバのインストール
2. hostapd.conf の設定
3. dnsmasq.conf の設定
4. iptables ルールの設定

---

## Phase 3: Flask アプリケーションのセットアップ

### 3.1 リポジトリのクローン

```bash
ssh pi@raspberrypi.local << 'EOF'
  # ホームディレクトリに移動
  cd ~
  
  # リポジトリをクローン
  git clone https://github.com/optic-ai/dual-wifi-temperature-monitoring.git temperature_server
  cd temperature_server
EOF
```

### 3.2 Python 仮想環境の作成

```bash
ssh pi@raspberrypi.local << 'EOF'
  cd ~/temperature_server
  
  # 仮想環境作成
  python3 -m venv venv
  
  # 仮想環境有効化
  source venv/bin/activate
  
  # pip アップグレード
  pip install --upgrade pip
EOF
```

### 3.3 依存ライブラリのインストール

```bash
ssh pi@raspberrypi.local << 'EOF'
  cd ~/temperature_server
  source venv/bin/activate
  
  # requirements.txt からインストール
  pip install -r requirements.txt
  
  # インストール確認
  pip list
EOF
```

### 3.4 データベース初期化

```bash
ssh pi@raspberrypi.local << 'EOF'
  cd ~/temperature_server
  source venv/bin/activate
  
  # テーブル作成
  python3 << 'PYTHON'
  from database.models import init_database
  init_database()
  print("✓ Database initialized")
  PYTHON
EOF
```

### 3.5 手動テスト実行

```bash
ssh pi@raspberrypi.local << 'EOF'
  cd ~/temperature_server
  source venv/bin/activate
  
  # Flask サーバーを起動（5秒後に Ctrl+C で終了）
  timeout 5 python3 run.py || true
  
  # ログに "Temperature Server Started!" が出ればOK
EOF
```

---

## Phase 4: systemd サービス登録

### 4.1 サービスファイルの作成

```bash
ssh pi@raspberrypi.local << 'EOF'
  # サービスファイルをコピー
  sudo cp ~/temperature_server/systemd/temperature-server.service \
    /etc/systemd/system/
  
  # サービスファイルを確認
  sudo cat /etc/systemd/system/temperature-server.service
EOF
```

### 4.2 systemd に認識させる

```bash
ssh pi@raspberrypi.local << 'EOF'
  # systemd をリロード
  sudo systemctl daemon-reload
  
  # サービスを有効化（起動時に自動開始）
  sudo systemctl enable temperature-server
  
  # サービスを開始
  sudo systemctl start temperature-server
  
  # 確認
  sudo systemctl status temperature-server
EOF
```

---

## Phase 5: 接続テスト

### 5.1 WiFi 接続確認

```bash
ssh pi@raspberrypi.local << 'EOF'
  # wlan1 (AP) が UP しているか確認
  ip addr show wlan1
  
  # wlan0 (Station) が接続しているか確認
  ip addr show wlan0
  
  # hostapd が動作しているか確認
  sudo systemctl status hostapd
  
  # dnsmasq が動作しているか確認
  sudo systemctl status dnsmasq
EOF
```

### 5.2 Flask サーバー確認

```bash
ssh pi@raspberrypi.local << 'EOF'
  # サーバーがリッスンしているか確認
  sudo netstat -tlnp | grep 5000
  
  # ログを確認
  sudo journalctl -u temperature-server -n 20
EOF
```

### 5.3 ネットワークテスト

```bash
ssh pi@raspberrypi.local << 'EOF'
  # localhost テスト
  curl -X POST http://127.0.0.1:5000/api/temperature \
    -H "Content-Type: application/json" \
    -d '{"device_id":"TEST","name":"test","location":"test","temperature":25.0}'
  
  # 192.168.4.1 テスト
  curl -X POST http://192.168.4.1:5000/api/temperature \
    -H "Content-Type: application/json" \
    -d '{"device_id":"TEST","name":"test","location":"test","temperature":25.0}'
  
  # 両方で 201 Created が返ればOK
EOF
```

---

## Phase 6: ESP32 コード配置

[ESP32_CODE.md](ESP32_CODE.md) を参照して、ESP32 に温度送信コードを書き込んでください。

---

## Phase 7: エンドツーエンドテスト

### 7.1 Web ダッシュボードアクセス

```
ブラウザで以下にアクセス：
http://192.168.11.57:5000/

※ IP アドレスは自分の環境に合わせて変更
```

### 7.2 ESP32 からのデータ受信確認

```bash
ssh pi@raspberrypi.local << 'EOF'
  # リアルタイムでログを監視（Ctrl+C で終了）
  sudo journalctl -u temperature-server -f
  
  # ESP32 がデータを送信していれば以下が見える：
  # "POST /api/temperature HTTP/1.1" 201
  # "Data saved - Device: ESP32_01, Temp: 23.5C"
EOF
```

### 7.3 データベースの確認

```bash
ssh pi@raspberrypi.local << 'EOF'
  cd ~/temperature_server
  source venv/bin/activate
  
  python3 << 'PYTHON'
  from database.queries import TemperatureQueries
  
  # 最新のデータを取得
  readings = TemperatureQueries.get_all_latest()
  
  if readings:
      print(f"✓ Found {len(readings)} sensor(s)")
      for r in readings:
          print(f"  Device: {r['device_id']}, Temp: {r['temperature']}°C")
  else:
      print("✗ No data found")
  PYTHON
EOF
```

---

## トラブルシューティング（セットアップ時）

### 問題：SSH で接続できない

```bash
# Raspberry Pi のローカルネットワークホスト名を確認
ssh pi@raspberrypi.local

# または IP アドレスで接続
ssh pi@192.168.11.200
```

### 問題：USB WiFi ドングルが認識されない

```bash
ssh pi@raspberrypi.local << 'EOF'
  # USB デバイスを確認
  lsusb | grep -i tp-link
  
  # 出力例：
  # Bus 001 Device 004: ID 2357:0120 TP-Link Archer T2U
  
  # 見つからない場合はドライバの再インストール
  cd /tmp
  git clone https://github.com/morrownr/8821au-20210708.git
  cd 8821au-20210708
  sudo ./install-driver.sh
  sudo reboot
EOF
```

### 問題：Flask が起動しない

```bash
ssh pi@raspberrypi.local << 'EOF'
  # ログを確認
  sudo journalctl -u temperature-server -n 50
  
  # 手動で実行して詳細なエラーを見る
  cd ~/temperature_server
  source venv/bin/activate
  python3 run.py
EOF
```

---

## 次のステップ

セットアップが完了したら：

1. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) をブックマーク
2. [LESSONS_LEARNED.md](LESSONS_LEARNED.md) で教訓を学ぶ
3. [ESP32_CODE.md](ESP32_CODE.md) で複数デバイス対応を検討

---

**最後に更新**: 2025年12月24日
