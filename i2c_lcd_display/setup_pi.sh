#!/bin/bash
# I2C 20x4 LCD 診断用セットアップ
set -e
cd "$(dirname "$0")"

echo "[1/4] I2C 有効化確認..."
if ! ls /dev/i2c-1 2>/dev/null; then
    echo "  I2C 未有効化。以下を実施してから再実行:"
    echo "    sudo raspi-config → Interface Options → I2C → Enable → Reboot"
    exit 1
fi
echo "  I2C OK"

echo "[2/4] I2C アドレス スキャン..."
if ! command -v i2cdetect &>/dev/null; then
    sudo apt install -y i2c-tools
fi
echo "  Bus 1 のデバイス:"
sudo i2cdetect -y 1

echo "[3/4] Python venv 作成 + 依存インストール..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "[4/4] 診断スクリプト実行 (Ctrl+C で終了)"
echo "      5 秒ごとにページが切り替わり、全キャラコードを順に表示"
echo ""
./venv/bin/python3 i2c_lcd_charmap_test.py
