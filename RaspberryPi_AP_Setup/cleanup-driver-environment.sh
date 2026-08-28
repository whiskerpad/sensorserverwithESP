#!/usr/bin/env bash
# ============================================================
# Archer T2U Plus ドライバー導入の検証前状態に戻すスクリプト
# ============================================================
#  実行: sudo bash cleanup-driver-environment.sh
#
#  目的:
#   ガイド「ArcherT2UPlus_ドライバー導入.md」の手順を最初から
#   検証できる状態に Raspberry Pi を戻す。OS は再フラッシュせず、
#   今までの作業で追加したものだけを撤去する。
#
#  撤去対象:
#   - DKMS に登録された rtl8812au モジュール
#   - ロード中の 8812au モジュール
#   - ~/8812au-20210820/ ディレクトリ (クローンしたソース)
#   - ~/88x2bu-20210702/ ディレクトリ (もし作っていれば)
#   - /etc/modules-load.d/8812au.conf (自動ロード設定)
#   - /etc/udev/rules.d/70-persistent-net.rules (MAC ベース命名固定)
#   - /etc/udev/rules.d/99-archer-t2u-plus.rules (USB ID 動的追加用 rule)
#   - /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf (unmanaged 設定)
#   - /tmp/hostapd-test.conf (AP テスト用一時設定)
#   - ~/install-driver*.log (インストールログ)
#   - dkms / build-essential / bc / linux-headers-rpi-* /
#     raspberrypi-kernel-headers (ビルド用に入れたパッケージ)
#   - hostapd (AP テスト用に入れたパッケージ)
#
#  撤去しないもの:
#   - git (Pi の運用で他にも使うため)
#   - OS の標準パッケージ
#   - wlan0 (オンボード Wi-Fi) の自宅/現場ルーターへの接続設定
#
#  実行後にリブートが必要 (スクリプト末尾で対話的に確認)。
# ============================================================

set -u   # 未定義変数で停止 (-e は付けない: 一部 || true で続行する)

# 端末カラー
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GRN}[CLEANUP]${NC} $*"; }
warn() { echo -e "${YLW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }

# 必ず root 権限で動かす
if [[ $EUID -ne 0 ]]; then
    err "このスクリプトは root 権限で実行してください (sudo bash $0)"
    exit 1
fi

# 実行前の最終確認
cat <<EOF

${YLW}===========================================================
このスクリプトは下記をすべて撤去します:
  - DKMS の rtl8812au モジュール
  - ~/8812au-20210820/ (および 88x2bu-20210702/)
  - /etc/modules-load.d/8812au.conf
  - /etc/udev/rules.d/70-persistent-net.rules
  - /etc/udev/rules.d/99-archer-t2u-plus.rules
  - /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf
  - /tmp/hostapd-test.conf
  - ~/install-driver*.log
  - dkms / build-essential / bc / カーネルヘッダ系
  - hostapd
===========================================================${NC}

EOF

read -p "本当に実行してよいですか? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then
    log "中止しました"
    exit 0
fi


# ------------------------------------------------------------
# 1. hostapd の停止
# ------------------------------------------------------------
log "1/10: 動作中の hostapd を停止"
systemctl stop hostapd 2>/dev/null || true
pkill -f hostapd 2>/dev/null || true


# ------------------------------------------------------------
# 2. ドライバーモジュールのアンロード
# ------------------------------------------------------------
log "2/10: 8812au モジュールをアンロード"
if lsmod | grep -q '^8812au'; then
    modprobe -r 8812au 2>/dev/null || warn "modprobe -r 8812au に失敗 (動作中のセッションがあるかも)"
else
    log "      → モジュール未ロード、スキップ"
fi


# ------------------------------------------------------------
# 3. DKMS からの削除
# ------------------------------------------------------------
log "3/10: DKMS からドライバーを削除"

# pi ユーザーのホームを推定 (sudo 実行下では HOME=/root のため)
PI_HOME=$(eval echo "~$SUDO_USER")

# remove-driver.sh が残っていればそれを優先
if [[ -x "$PI_HOME/8812au-20210820/remove-driver.sh" ]]; then
    log "      → $PI_HOME/8812au-20210820/remove-driver.sh を実行"
    (cd "$PI_HOME/8812au-20210820" && bash remove-driver.sh) || warn "remove-driver.sh が一部失敗"
fi

# それでも DKMS に残っていれば手動で削除
dkms status 2>/dev/null | grep -i 'rtl8812au\|8812au' | while read line; do
    name_ver=$(echo "$line" | awk -F',' '{print $1}' | tr -d ' ')
    log "      → dkms remove $name_ver --all"
    dkms remove "$name_ver" --all 2>/dev/null || warn "dkms remove $name_ver 失敗"
done


# ------------------------------------------------------------
# 4. ドライバーソースディレクトリの削除
# ------------------------------------------------------------
log "4/10: クローンしたソースディレクトリを削除"

for dir in "$PI_HOME/8812au-20210820" "$PI_HOME/88x2bu-20210702"; do
    if [[ -d "$dir" ]]; then
        rm -rf "$dir"
        log "      → $dir を削除"
    fi
done


# ------------------------------------------------------------
# 5. modules-load 自動ロード設定の削除
# ------------------------------------------------------------
log "5/10: /etc/modules-load.d/8812au.conf を削除"
rm -f /etc/modules-load.d/8812au.conf


# ------------------------------------------------------------
# 6. udev rule の削除 (命名固定 + new_id 自動追加)
# ------------------------------------------------------------
log "6/10: udev rule を削除"
rm -f /etc/udev/rules.d/70-persistent-net.rules
rm -f /etc/udev/rules.d/99-archer-t2u-plus.rules
udevadm control --reload-rules 2>/dev/null || true


# ------------------------------------------------------------
# 7. NetworkManager unmanaged 設定の削除
# ------------------------------------------------------------
log "7/10: /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf を削除"
rm -f /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf
systemctl restart NetworkManager 2>/dev/null || true


# ------------------------------------------------------------
# 8. テスト用一時設定とログの削除
# ------------------------------------------------------------
log "8/10: テスト用一時設定とログを削除"
rm -f /tmp/hostapd-test.conf
rm -f "$PI_HOME"/install-driver*.log


# ------------------------------------------------------------
# 9. パッケージのアンインストール
# ------------------------------------------------------------
log "9/10: ビルド用・テスト用パッケージをアンインストール"

# ヘッダ系をまとめて削除 (存在しないものはスキップ)
HEADER_PKGS=(
    "linux-headers-rpi-v8"
    "linux-headers-rpi-v8-2712"
    "linux-headers-rpi-2712"
    "linux-headers-rpi-v7l"
    "linux-headers-rpi-v6"
    "raspberrypi-kernel-headers"
)

PKGS_TO_REMOVE=("dkms" "build-essential" "bc" "hostapd")

# 実際にインストールされているパッケージだけリストに追加
for pkg in "${HEADER_PKGS[@]}"; do
    if dpkg -l "$pkg" 2>/dev/null | grep -q '^ii'; then
        PKGS_TO_REMOVE+=("$pkg")
    fi
done

# uname -r 対応のヘッダも念のため
CURRENT_HEADER="linux-headers-$(uname -r)"
if dpkg -l "$CURRENT_HEADER" 2>/dev/null | grep -q '^ii'; then
    PKGS_TO_REMOVE+=("$CURRENT_HEADER")
fi

log "      → 削除対象: ${PKGS_TO_REMOVE[*]}"
apt-get remove --purge -y "${PKGS_TO_REMOVE[@]}" 2>/dev/null || \
    warn "一部パッケージの削除に失敗"

log "      → apt autoremove で依存も整理"
apt-get autoremove --purge -y 2>/dev/null || true


# ------------------------------------------------------------
# 10. 完了確認
# ------------------------------------------------------------
echo
log "10/10: クリーンアップ完了。下記の確認結果がすべて「なし」なら成功"
echo
echo "  [ロード中モジュール]"
lsmod | grep 8812au || echo "    (なし) ← 期待値"
echo
echo "  [DKMS 登録状態]"
dkms status 2>/dev/null | grep -i '8812au\|rtl8812' || echo "    (なし) ← 期待値"
echo
echo "  [残存ファイル/ディレクトリ]"
[[ -d "$PI_HOME/8812au-20210820" ]] && echo "    8812au-20210820: 残存!" || echo "    8812au-20210820: なし ← 期待値"
[[ -f /etc/modules-load.d/8812au.conf ]] && echo "    modules-load.d/8812au.conf: 残存!" || echo "    modules-load.d/8812au.conf: なし ← 期待値"
[[ -f /etc/udev/rules.d/70-persistent-net.rules ]] && echo "    70-persistent-net.rules: 残存!" || echo "    70-persistent-net.rules: なし ← 期待値"
[[ -f /etc/udev/rules.d/99-archer-t2u-plus.rules ]] && echo "    99-archer-t2u-plus.rules: 残存!" || echo "    99-archer-t2u-plus.rules: なし ← 期待値"
[[ -f /etc/NetworkManager/conf.d/99-unmanaged-wlan1.conf ]] && echo "    99-unmanaged-wlan1.conf: 残存!" || echo "    99-unmanaged-wlan1.conf: なし ← 期待値"
[[ -f /tmp/hostapd-test.conf ]] && echo "    /tmp/hostapd-test.conf: 残存!" || echo "    /tmp/hostapd-test.conf: なし ← 期待値"
echo
echo "  [パッケージ]"
dpkg -l 2>/dev/null | grep -E '^ii  (dkms|build-essential|linux-headers-rpi|hostapd)' || echo "    (なし) ← 期待値"

echo
log "リブートで完全に初期状態に戻ります。"
read -p "今すぐリブートしますか? (yes/no): " do_reboot
if [[ "$do_reboot" == "yes" ]]; then
    log "リブートします..."
    sleep 2
    reboot
else
    log "リブートは手動で行ってください: sudo reboot"
fi
