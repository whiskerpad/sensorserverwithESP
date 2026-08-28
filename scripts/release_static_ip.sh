#!/bin/bash
# ============================================================
#  release_static_ip.sh
#
#  Raspberry Pi の wlan0 静的 IP を解除して DHCP に戻す。
#  Tailscale 導入により LAN IP に依存しない構成が可能になったため。
#
#  対象: wlan0 のみ (wlan1 = AP 192.168.4.1 は絶対に触らない)
#  対応: NetworkManager (nmcli) と dhcpcd の両方を自動判別
#  冪等: 何度実行しても壊れない
#  非対話: プロンプト無し
#
#  実行:
#    sudo bash release_static_ip.sh
#
#  ロールバック手順は docs/Pi_wlan0_DHCP化ガイド.md §5 参照
# ============================================================
set -euo pipefail

BACKUP_DIR="/etc/backup_wlan0_$(date +%Y%m%d_%H%M%S)"
IFACE="wlan0"

echo "==================================================="
echo " Pi wlan0 静的 IP 解除スクリプト"
echo "   IFACE       : $IFACE"
echo "   BACKUP_DIR  : $BACKUP_DIR"
echo "==================================================="

# ----------- 実行権限確認 -----------
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: sudo で実行してください" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# ----------- 事前情報の保存 -----------
echo "[info] 現状バックアップ → $BACKUP_DIR/"
ip -4 addr show "$IFACE" > "$BACKUP_DIR/ip_addr_before.txt" 2>&1 || true
ip -4 route                > "$BACKUP_DIR/ip_route_before.txt" 2>&1 || true
nmcli -t con show          > "$BACKUP_DIR/nmcli_con_before.txt" 2>&1 || true
[ -f /etc/dhcpcd.conf ] && cp /etc/dhcpcd.conf "$BACKUP_DIR/dhcpcd.conf.orig" || true

# ----------- 機構判定 -----------
NM_ACTIVE=false
DHCPCD_ACTIVE=false
DHCPCD_HAS_STATIC=false

systemctl is-active --quiet NetworkManager && NM_ACTIVE=true
systemctl is-active --quiet dhcpcd && DHCPCD_ACTIVE=true

if [ -f /etc/dhcpcd.conf ] && grep -qE "^[[:space:]]*interface[[:space:]]+${IFACE}" /etc/dhcpcd.conf; then
    DHCPCD_HAS_STATIC=true
fi

echo "[detect] NetworkManager active : $NM_ACTIVE"
echo "[detect] dhcpcd active         : $DHCPCD_ACTIVE"
echo "[detect] dhcpcd has $IFACE cfg : $DHCPCD_HAS_STATIC"

CHANGED=false

# ----------- NetworkManager 側処理 -----------
if [ "$NM_ACTIVE" = true ]; then
    # wlan0 に紐付いた wifi 接続を全て探す
    CON_NAMES=$(nmcli -t -f NAME,DEVICE,TYPE con show \
        | awk -F: -v dev="$IFACE" '$2==dev && $3~/wireless|wifi/ {print $1}')

    if [ -z "$CON_NAMES" ]; then
        echo "[nm] $IFACE に紐付いた wifi 接続なし (SKIP)"
    else
        while IFS= read -r CON_NAME; do
            METHOD=$(nmcli -t -g ipv4.method con show "$CON_NAME" 2>/dev/null || echo "")
            echo "[nm] $CON_NAME (現 ipv4.method=$METHOD)"

            if [ "$METHOD" = "manual" ]; then
                echo "     → auto (DHCP) に変更"
                nmcli con modify "$CON_NAME" ipv4.method auto
                nmcli con modify "$CON_NAME" ipv4.addresses ""
                nmcli con modify "$CON_NAME" ipv4.gateway ""
                nmcli con modify "$CON_NAME" ipv4.dns ""
                CHANGED=true
            else
                echo "     → 既に auto。変更不要 (SKIP)"
            fi
        done <<< "$CON_NAMES"

        if [ "$CHANGED" = true ]; then
            # 各接続を down → up (最後の 1 個で反映)
            while IFS= read -r CON_NAME; do
                nmcli con down "$CON_NAME" 2>/dev/null || true
                nmcli con up   "$CON_NAME" 2>/dev/null || true
            done <<< "$CON_NAMES"
        fi
    fi
fi

# ----------- dhcpcd 側処理 -----------
if [ "$DHCPCD_HAS_STATIC" = true ]; then
    echo "[dhcpcd] /etc/dhcpcd.conf の $IFACE ブロックをコメントアウト"
    # interface wlan0 から次の空行までを '# ' プレフィックスに
    sed -i "/^[[:space:]]*interface[[:space:]]\+${IFACE}[[:space:]]*$/,/^[[:space:]]*$/{s/^\([^#]\)/# \1/}" /etc/dhcpcd.conf
    CHANGED=true

    if [ "$DHCPCD_ACTIVE" = true ]; then
        echo "[dhcpcd] restart"
        systemctl restart dhcpcd
    fi
fi

# ----------- 結果表示 -----------
echo ""
echo "==================================================="
if [ "$CHANGED" = true ]; then
    echo " 変更適用済。5 秒待って新 IP を確認..."
    sleep 5
else
    echo " 変更なし (既に DHCP 化されている可能性)。現状を表示..."
fi
echo "---"
ip -4 addr show "$IFACE" | grep -E "inet|state" || true
echo "---"
echo " Backup: $BACKUP_DIR/"
echo " Roll back guide: docs/Pi_wlan0_DHCP化ガイド.md §5"
echo "==================================================="
echo ""
echo " ★ wlan1 (AP) 確認: 192.168.4.1 が変わっていないか"
ip -4 addr show wlan1 2>/dev/null | grep inet || echo "   (wlan1 見えず)"
