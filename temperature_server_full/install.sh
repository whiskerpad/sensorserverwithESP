#!/bin/bash
# ============================================================
#  temperature_server 一括インストーラ (非対話、冪等)
#
#  想定環境:
#    Raspberry Pi OS (Debian) Trixie / Bookworm
#    Python 3.11+ (Trixie は 3.13、Bookworm は 3.11)
#    ユーザ: pi
#    設置先: /home/pi/temperature_server
#
#  実行:
#    cd /home/pi/temperature_server && bash install.sh
#
#  冪等性:
#    - 既に venv があれば再作成せず pip install だけ実行
#    - systemd unit は毎回上書き配置 → daemon-reload → restart
#    - 質問プロンプトなし
# ============================================================
set -euo pipefail

# ----------- 定数 -----------
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="temperature-server"
SERVICE_SRC="$INSTALL_DIR/systemd/${SERVICE_NAME}.service"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="$INSTALL_DIR/venv"
REQ_FILE="$INSTALL_DIR/requirements.txt"

echo "==================================================="
echo " temperature_server installer"
echo "   INSTALL_DIR : $INSTALL_DIR"
echo "   VENV_DIR    : $VENV_DIR"
echo "==================================================="

# ----------- 前提: OS パッケージ -----------
echo "[1/5] apt: python3-venv / v4l-utils / opencv 依存"
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    python3-venv \
    python3-pip \
    v4l-utils \
    libatlas-base-dev

# ----------- venv 準備 -----------
echo "[2/5] Python venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "   created new venv"
else
    echo "   reuse existing venv"
fi

# ----------- pip install -----------
echo "[3/5] pip install"
"$VENV_DIR/bin/pip" install --upgrade pip wheel setuptools
"$VENV_DIR/bin/pip" install -r "$REQ_FILE"

# ----------- systemd unit -----------
echo "[4/5] systemd unit"
if [ ! -f "$SERVICE_SRC" ]; then
    echo "   ERROR: $SERVICE_SRC が見つかりません" >&2
    exit 1
fi
sudo cp "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

# ----------- 起動 (再起動安全) -----------
echo "[5/5] systemctl restart"
sudo systemctl restart "$SERVICE_NAME"
sleep 3
sudo systemctl status "$SERVICE_NAME" --no-pager | head -15

echo ""
echo "==================================================="
echo " Done."
echo "   Dashboard: http://<Pi-IP>:5000/"
echo "   Stream   : http://<Pi-IP>:5000/stream"
echo "   Journal  : sudo journalctl -u $SERVICE_NAME -f"
echo "==================================================="
