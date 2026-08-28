#!/bin/bash
# ============================================================
#  Master device_id マイグレーション (2026-08-15)
#
#  背景:
#    ESP32_ESPNOW_Master.ino が MAC ベース ID "MST-XXXXXX" に移行した。
#    それ以前は device_id="ESP32_MAIN" 固定。DB に残る旧レコードの
#    device_id を新 ID にマッピング更新する。
#
#  使い方 (Pi bash):
#    cd /home/pi/temperature_server
#    ./venv/bin/python3 - <<'PY'
#    ... (このスクリプトが実際にやる作業を Python でやる方が安全)
#    PY
#
#  ただし device_id の変更対象は temperatures テーブル (履歴)。
#  ESP-NOW 経由で送られてくる sensors[] の内側 sensor_id は "NOW-XXXXXX"
#  として個別に既に保存されているので触らない。
#
#  つまりこのマイグレーションで書換えるものは実質「device_nicknames」だけで、
#  旧 "ESP32_MAIN" に付けていた nickname を新 MST-XXXXXX へ移すだけ。
#  temperatures 側は sensor_id が個別なので更新不要。
#
#  実行前:
#    1. Master スケッチを新版に更新 → 起動 → Serial に master_hello が出る
#    2. Pi の temperature-server を再起動 → serial_reader が新 MST-XXXXXX を
#       device_nicknames に自己登録する
#    3. 新旧の ID を確認:
#         sqlite3 data/temperature.db "SELECT * FROM device_nicknames WHERE sensor_id LIKE 'MST-%' OR sensor_id='ESP32_MAIN';"
#    4. 本スクリプトを実行して旧 nickname を新 ID に移動
# ============================================================
set -euo pipefail

DB_PATH="${DB_PATH:-/home/pi/temperature_server/data/temperature.db}"
NEW_MASTER_ID="${1:-}"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: DB not found: $DB_PATH" >&2
    exit 1
fi

if [ -z "$NEW_MASTER_ID" ]; then
    echo "使い方: $0 <新 Master device_id>"
    echo "  例: $0 MST-A1B2C3"
    echo ""
    echo "現在の device_nicknames から候補を表示:"
    sqlite3 "$DB_PATH" \
        "SELECT sensor_id, nickname, updated_at FROM device_nicknames WHERE sensor_id LIKE 'MST-%' OR sensor_id='ESP32_MAIN' ORDER BY updated_at DESC;"
    exit 1
fi

# バックアップ
BACKUP="${DB_PATH}.bak.$(date +%Y%m%d_%H%M%S)"
cp "$DB_PATH" "$BACKUP"
echo "Backup: $BACKUP"

# 旧 ESP32_MAIN に nickname があれば、新 MST-XXXXXX に移送
OLD_NICK=$(sqlite3 "$DB_PATH" "SELECT nickname FROM device_nicknames WHERE sensor_id='ESP32_MAIN';")

if [ -n "$OLD_NICK" ]; then
    echo "旧 ESP32_MAIN の nickname='$OLD_NICK' を $NEW_MASTER_ID に移送"
    sqlite3 "$DB_PATH" <<SQL
BEGIN;
-- 新 ID の nickname を旧値で上書き (既存の自動登録デフォルト名を置換)
UPDATE device_nicknames
   SET nickname = '$OLD_NICK', updated_at = CURRENT_TIMESTAMP
 WHERE sensor_id = '$NEW_MASTER_ID';
-- 旧レコードは削除
DELETE FROM device_nicknames WHERE sensor_id='ESP32_MAIN';
COMMIT;
SQL
    echo "移送完了。"
else
    echo "旧 ESP32_MAIN の nickname は無し。何もしません。"
fi

echo ""
echo "現在の Master nickname:"
sqlite3 "$DB_PATH" \
    "SELECT sensor_id, nickname, updated_at FROM device_nicknames WHERE sensor_id LIKE 'MST-%';"
