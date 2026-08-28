#!/bin/bash
# I2C LCD 拡張機能 (半角カナ + カスタムアイコン) 反映
set -e
cd "$(dirname "$0")"

echo "[1/3] jaconv インストール (venv 内)..."
./venv/bin/pip install jaconv

echo "[2/3] サービス再起動 (更新版 i2c_lcd_display.py を適用)..."
sudo systemctl restart i2c-lcd-display
sleep 3

echo "[3/3] 状態確認..."
sudo systemctl status i2c-lcd-display --no-pager | head -10
echo ""
echo "ログ観察: sudo journalctl -u i2c-lcd-display -f"
echo "  → 'CGRAM: 5 RSSI bars + camera + AP + WLAN icons' が出れば拡張機能 OK"
