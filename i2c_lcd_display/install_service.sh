#!/bin/bash
# ============================================================
#  I2C LCD Display 一括インストーラ (非対話、冪等)
#
#  想定環境:
#    Raspberry Pi OS Trixie / Bookworm、I2C 有効化済
#    HD44780 20x4 + PCF8574 I2C バックパック
#    設置先: /home/pi/i2c_lcd_display
#
#  実行:
#    cd /home/pi/i2c_lcd_display && bash install_service.sh
#
#  I2C アドレスの決定順位:
#    1. 環境変数 LCD_I2C_ADDR (例: LCD_I2C_ADDR=0x3F bash install_service.sh)
#    2. i2cdetect -y 1 の出力から 1 個だけ検出できた場合はそれを採用
#    3. 複数検出時は 0x27 をデフォルトとして進める (systemd unit のコメントで変更可能)
#
#  冪等性:
#    - 再実行しても venv は再作成しない (pip install のみ)
#    - systemd unit は毎回上書き
# ============================================================
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="i2c-lcd-display"
SERVICE_SRC="$INSTALL_DIR/${SERVICE_NAME}.service"
SERVICE_DST="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="$INSTALL_DIR/venv"
REQ_FILE="$INSTALL_DIR/requirements.txt"

echo "==================================================="
echo " I2C LCD Display installer"
echo "   INSTALL_DIR : $INSTALL_DIR"
echo "==================================================="

# ----------- 前提: I2C 有効化 -----------
if [ ! -e /dev/i2c-1 ]; then
    echo "ERROR: /dev/i2c-1 がありません。" >&2
    echo "  sudo raspi-config → Interface Options → I2C → Enable → Reboot" >&2
    exit 1
fi

# ----------- 前提: i2c-tools -----------
if ! command -v i2cdetect &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends i2c-tools python3-venv
fi

# ----------- I2C アドレス確定 (非対話) -----------
if [ -n "${LCD_I2C_ADDR:-}" ]; then
    ADDR="$LCD_I2C_ADDR"
    echo "[addr] env override: $ADDR"
else
    # i2cdetect -y 1 の出力から 0x30-0x7f 範囲の 2 桁 hex を拾う
    DETECTED=$(sudo i2cdetect -y 1 2>/dev/null \
        | tail -n +2 \
        | awk 'NR>0 { for(i=2;i<=NF;i++) if($i ~ /^[0-9a-fA-F]{2}$/) print "0x"$i }')
    COUNT=$(echo "$DETECTED" | grep -c . || true)
    if [ "$COUNT" -eq 1 ]; then
        ADDR="$DETECTED"
        echo "[addr] auto-detected: $ADDR"
    elif [ "$COUNT" -gt 1 ]; then
        ADDR="0x27"
        echo "[addr] multiple detected: $DETECTED"
        echo "       fallback to default: $ADDR (変更するには LCD_I2C_ADDR 環境変数で再実行)"
    else
        ADDR="0x27"
        echo "[addr] none detected. fallback to default: $ADDR"
        echo "       (バックパックの結線 or 電源を確認してから再実行)"
    fi
fi

# ----------- venv 準備 -----------
echo "[venv] Python venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "   created new venv"
else
    echo "   reuse existing venv"
fi

# ----------- pip install -----------
echo "[pip] install requirements"
"$VENV_DIR/bin/pip" install --upgrade pip wheel
"$VENV_DIR/bin/pip" install -r "$REQ_FILE"

# ----------- systemd unit -----------
echo "[systemd] install unit with LCD_I2C_ADDR=$ADDR"
if [ ! -f "$SERVICE_SRC" ]; then
    echo "ERROR: $SERVICE_SRC が見つかりません" >&2
    exit 1
fi
# unit 内の LCD_I2C_ADDR を書換えて配置
sudo sed "s|Environment=\"LCD_I2C_ADDR=.*\"|Environment=\"LCD_I2C_ADDR=$ADDR\"|" \
    "$SERVICE_SRC" | sudo tee "$SERVICE_DST" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

# ----------- 起動 -----------
echo "[start] systemctl restart"
sudo systemctl restart "$SERVICE_NAME"
sleep 3
sudo systemctl status "$SERVICE_NAME" --no-pager | head -15

echo ""
echo "==================================================="
echo " Done."
echo "   Journal: sudo journalctl -u $SERVICE_NAME -f"
echo "   Change addr later: sudo systemctl edit $SERVICE_NAME"
echo "==================================================="
