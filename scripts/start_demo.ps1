# 舆镜 · DEMO 模式一键启动（答辩演示专用）
# 行为：数据冻结，不启动任何爬虫；其他功能（聚类/早报/AI/检索）照常。
#   - 后端 YUJING_DEMO_MODE=1
#     * 跳过 8 个爬虫 source 定时 job
#     * sync_trigger_crawlers 入口短路（手动刷新/SWR 也不爬）
#     * 数据库仍是主库 runtime/db/yujing.db
#   - 前端 VITE_DEMO_MODE=1（供 UI 显示「演示模式」角标用）
#
# 使用：powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  舆镜 DEMO 模式启动（数据冻结，不爬取）" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 后端
$env:YUJING_DEMO_MODE = '1'
$backend = Start-Process -PassThru -FilePath 'python' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $root
Write-Host "[OK] 后端 PID=$($backend.Id)" -ForegroundColor Green

# 前端
$env:VITE_DEMO_MODE = '1'
$frontend = Start-Process -PassThru -FilePath 'npm' -ArgumentList 'run','dev' -WorkingDirectory (Join-Path $root 'yujing-ui')
Write-Host "[OK] 前端 PID=$($frontend.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "等待服务就绪... (30s)" -ForegroundColor Yellow
Start-Sleep -Seconds 30

try {
    $r = Invoke-WebRequest 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 5
    Write-Host "[健康] 后端 HTTP $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Warning "后端尚未就绪: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "前端: http://localhost:5173" -ForegroundColor Cyan
Write-Host "后端: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "停止: 手动 kill PID $($backend.Id), $($frontend.Id)" -ForegroundColor Cyan
