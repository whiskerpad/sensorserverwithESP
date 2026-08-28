# [DEPRECATED 2026-07-17]
#
# 元は元プロジェクト用の PowerShell 更新スクリプトで、以下のような古い前提を持っていました:
#   - $User = "takemetothehospital"   (ホスト名を username と誤認、正しくは pi)
#   - $ProjectPath = "/home/takemetothehospital/temperature_monitoring/temperature_server"
#     (実際の Pi 側パスは /home/pi/temperature_server)
#
# 代わりに outputs/temperature_server_deploy/deploy_cleanup.ps1 を使ってください。
#
# このファイルは削除対象。

Write-Host "[DEPRECATED] Use outputs\temperature_server_deploy\deploy_cleanup.ps1 instead" -ForegroundColor Yellow
