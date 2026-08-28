# ============================================================
#  device_id 重複検知 + rssi/signal_strength 両対応 の差分反映
#  (2026-07-28)
#
#  変更範囲:
#    - app/routes/api.py: _last_ip_per_sensor 追加、rssi/signal_strength 両受理
# ============================================================

$PiUser = "pi"
$PiIP   = "192.168.11.200"
$Src    = "Z:\afterNK\ESPSARVER\outputs\temperature_server_full"
$Dst    = "$PiUser@${PiIP}:/home/pi/temperature_server"

$files = @("app\routes\api.py")

Write-Host "=== Duplicate detect deploy ($($files.Count) file) ===" -ForegroundColor Cyan
foreach ($f in $files) {
    $srcPath = Join-Path $Src $f
    $dstRel  = $f -replace '\\', '/'
    Write-Host "-> $f" -ForegroundColor Yellow
    scp $srcPath "${Dst}/$dstRel"
}

Write-Host ""
Write-Host "Next: ssh pi@192.168.11.200 'sudo systemctl restart temperature-server'" -ForegroundColor Cyan
