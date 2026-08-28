#!/bin/bash
# ============================================================
#  Nokia 5110 表示機能 Pi 側セットアップスクリプト
#
#  実行前提: このスクリプトを /home/pi/nokia5110_display/ に配置してから
#  sudo bash /home/pi/nokia5110_display/setup_pi.sh
# ============================================================
set -e

cd "$(dirname "$0")"

echo "[1/6] SPI インターフェース有効化確認..."
if ! lsmod | grep -q spi_bcm2835; then
    echo "  SPI 未有効化。raspi-config で有効化してください:"
    echo "  sudo raspi-config → Interface Options → SPI → Enable → Reboot"
    echo "  完了後に本スクリプトを再実行"
    exit 1
fi
echo "  SPI OK"

echo "[2/6] 日本語フォント インストール..."
sudo apt update
sudo apt install -y fonts-noto-cjk fonts-mplus python3-venv python3-dev libjpeg-dev zlib1g-dev libfreetype-dev

echo "[3/6] Python venv 作成..."
python3 -m venv venv

echo "[4/6] Python 依存インストール..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "[5/6] systemd unit 反映..."
sudo cp nokia-display.service /etc/systemd/system/nokia-display.service
sudo systemctl daemon-reload
sudo systemctl enable nokia-display.service

echo "[6/6] サービス起動..."
sudo systemctl start nokia-display.service
sleep 2
sudo systemctl status nokia-display.service --no-pager | head -15

echo ""
echo "=== セットアップ完了 ==="
echo "ログ観察: sudo journalctl -u nokia-display -f"
echo "配線確認 (電源切って): docs 参照"
