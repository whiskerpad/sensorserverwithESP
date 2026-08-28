# ============================================================
#  3 層分離アーキテクチャ移行 (2026-07-30)
#
#  変更内容:
#    - ESP スケッチ 5 種を MAC ベース device_id + DHCP に全面切替 (Z: のみ、Pi 影響なし)
#    - Flask 側 api.py: 既に rssi/signal_strength 両受理 + 重複検知実装済
#    - Pi 側 dnsmasq.conf: MAC-IP 予約を追加する手動作業のみ (このスクリプトでは触らない)
#
#  このスクリプトの役割:
#    - Flask 側 api.py の最新版を Pi に反映 (前回未反映の場合の保険)
#    - 手動作業手順を画面表示
#
#  使い方: PowerShell で
#      cd Z:\afterNK\ESPSARVER\outputs\temperature_server_deploy
#      .\deploy_3layer_architecture.ps1
# ============================================================

$PiUser = "pi"
$PiIP   = "192.168.11.200"
$Src    = "Z:\afterNK\ESPSARVER\outputs\temperature_server_full"
$Dst    = "$PiUser@${PiIP}:/home/pi/temperature_server"

# Flask 側の最新 api.py を送信 (念のため再送)
Write-Host "=== Flask 側 api.py の最新版を反映 ===" -ForegroundColor Cyan
scp "$Src\app\routes\api.py" "${Dst}/app/routes/api.py"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  OK" -ForegroundColor Green
} else {
    Write-Host "  FAILED" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== 手動作業手順 (Pi 側 SSH で実行) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1) Flask サービス再起動" -ForegroundColor Yellow
Write-Host "     ssh pi@192.168.11.200"
Write-Host "     sudo systemctl restart temperature-server"
Write-Host "     sudo systemctl status temperature-server --no-pager -l"
Write-Host ""
Write-Host "2) 既存 ESP チップの MAC 取得 [すでに接続実績があれば]" -ForegroundColor Yellow
Write-Host "     sudo journalctl -u dnsmasq --since '1 hour ago' | grep -i DHCP"
Write-Host ""
Write-Host "3) dnsmasq に MAC-IP 予約を追加" -ForegroundColor Yellow
Write-Host "     sudo nano /etc/dnsmasq.d/wlan1.conf"
Write-Host '     -> 末尾に 1 行追加:'
Write-Host '       dhcp-host=[MAC],192.168.4.208,[hostname]'
Write-Host "     sudo systemctl restart dnsmasq"
Write-Host ""
Write-Host "4) ESP チップに新スケッチ [MAC ベース] を書込み" -ForegroundColor Yellow
Write-Host "     Arduino IDE で outputs/ESP8266_DeepSleep_FixedIP_Sensor/ を開く"
Write-Host "     -> 書換え無しでコピペ書込み"
Write-Host ""
Write-Host "5) ダッシュボードで動作確認 + nickname 割当" -ForegroundColor Yellow
Write-Host "     http://192.168.11.200:5000/management -> 表示名管理タブ"
Write-Host ""
Write-Host "詳細は outputs/temperature_server_deploy/dnsmasq_mac_reservation.md" -ForegroundColor Cyan
