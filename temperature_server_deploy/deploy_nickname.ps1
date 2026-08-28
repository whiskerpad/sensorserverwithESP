# ============================================================
#  Nickname 機能追加の差分反映 (2026-07-17)
#
#  変更範囲:
#    - database/models.py: device_nicknames テーブル追加
#    - database/queries.py: NicknameQueries クラス追加、get_all_latest 更新
#    - app/routes/api.py: 3 エンドポイント追加 (/api/nicknames)
#    - templates/management.html: 表示名管理タブ追加
#    - templates/dashboard.html: nickname 優先表示ロジック
#
#  使い方: PowerShell で
#      cd Z:\afterNK\ESPSARVER\outputs\temperature_server_deploy
#      .\deploy_nickname.ps1
# ============================================================

$PiUser = "pi"
$PiIP   = "192.168.11.200"
$Src    = "Z:\afterNK\ESPSARVER\outputs\temperature_server_full"
$Dst    = "$PiUser@${PiIP}:/home/pi/temperature_server"

$files = @(
    "database\models.py",
    "database\queries.py",
    "app\routes\api.py",
    "templates\management.html",
    "templates\dashboard.html"
)

Write-Host "=== Nickname feature deploy ($($files.Count) files) ===" -ForegroundColor Cyan
$fail = 0
foreach ($f in $files) {
    $srcPath = Join-Path $Src $f
    $dstRel  = $f -replace '\\', '/'
    $dstPath = "${Dst}/$dstRel"
    Write-Host "-> $f" -ForegroundColor Yellow
    scp $srcPath $dstPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   FAILED" -ForegroundColor Red
        $fail++
    }
}

if ($fail -eq 0) {
    Write-Host ""
    Write-Host "All $($files.Count) files transferred successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next: SSH to Pi and restart service:" -ForegroundColor Cyan
    Write-Host "    ssh pi@192.168.11.200"
    Write-Host "    sudo systemctl restart temperature-server"
    Write-Host "    sudo systemctl status temperature-server --no-pager -l"
    Write-Host ""
    Write-Host "After restart, browser check:" -ForegroundColor Cyan
    Write-Host "    http://192.168.11.200:5000/management  (see the new '表示名管理' tab)"
    Write-Host "    http://192.168.11.200:5000/            (dashboard uses nickname if set)"
} else {
    Write-Host ""
    Write-Host "$fail files failed to transfer" -ForegroundColor Red
}
