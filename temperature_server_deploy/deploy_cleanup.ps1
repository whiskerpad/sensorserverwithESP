# ============================================================
#  Cleanup 差分反映スクリプト (2026-07-17 audit)
#  使い方: PowerShell で以下を実行
#      cd Z:\afterNK\ESPSARVER\outputs\temperature_server_deploy
#      .\deploy_cleanup.ps1
# ============================================================

$PiUser = "pi"
$PiIP   = "192.168.11.200"
$Src    = "Z:\afterNK\ESPSARVER\outputs\temperature_server_full"
$Dst    = "$PiUser@${PiIP}:/home/pi/temperature_server"

$files = @(
    "run.py",
    "app\__init__.py",
    "app\routes\api.py",
    "app\routes\api_improved.py",
    "app\routes\dashboard.py",
    "database\queries.py",
    "services\background_tasks.py",
    "cli\management_cli.py",
    "templates\management.html",
    "templates\test_api.html",
    "templates\stream.html",
    "templates\video_feed_frame.html",
    "docs\AUDIT_20260717.md"
)

Write-Host "=== Cleanup deploy ($($files.Count) files) ===" -ForegroundColor Cyan
$fail = 0
foreach ($f in $files) {
    $srcPath = Join-Path $Src $f
    # Windows パス区切りを Linux 区切りに (scp destination path)
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
} else {
    Write-Host ""
    Write-Host "$fail files failed to transfer" -ForegroundColor Red
}
