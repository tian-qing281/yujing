# 舆镜 · DEMO 模式一键启动（答辩演示专用）
# 行为：
#   - 后端 YUJING_DEMO_MODE=1（用 yujing.demo.db、跳过全部定时任务）
#   - 前端 VITE_DEMO_MODE=1（拉长轮询、错误静默）
#   - 不启用 BERT/HF 在线下载，避免无网络时卡顿
#
# 使用：powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  舆镜 DEMO 模式启动" -ForegroundColor Cyan
Write-Host "  - 数据库: runtime\db\yujing.demo.db" -ForegroundColor Cyan
Write-Host "  - 定时任务: 全部跳过" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 验证 demo 库存在
$demoDb = Join-Path $root 'runtime\db\yujing.demo.db'
if (-not (Test-Path $demoDb)) {
    Write-Warning "未找到 $demoDb"
    Write-Warning "请先运行: Copy-Item runtime\db\yujing.db runtime\db\yujing.demo.db"
    exit 1
}

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
Write-Host "停止: scripts\stop_demo.ps1 或手动 kill PID $($backend.Id), $($frontend.Id)" -ForegroundColor Cyan
