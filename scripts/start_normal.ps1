# 舆镜 · 正常模式一键启动（开发/生产共用）
# 行为：完全等同于不带任何环境变量直接 uvicorn + npm run dev。
# 与 start_demo.ps1 对称，方便切换。
#
# 使用：powershell -ExecutionPolicy Bypass -File scripts\start_normal.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  舆镜 正常模式启动" -ForegroundColor Cyan
Write-Host "  - 数据库: runtime\db\yujing.db" -ForegroundColor Cyan
Write-Host "  - 定时任务: 正常注册" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# 确保未污染 DEMO 环境
Remove-Item Env:YUJING_DEMO_MODE -ErrorAction SilentlyContinue
Remove-Item Env:VITE_DEMO_MODE -ErrorAction SilentlyContinue

$backend = Start-Process -PassThru -FilePath 'python' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $root
Write-Host "[OK] 后端 PID=$($backend.Id)" -ForegroundColor Green

$frontend = Start-Process -PassThru -FilePath 'npm' -ArgumentList 'run','dev' -WorkingDirectory (Join-Path $root 'yujing-ui')
Write-Host "[OK] 前端 PID=$($frontend.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "前端: http://localhost:5173" -ForegroundColor Cyan
Write-Host "后端: http://127.0.0.1:8000" -ForegroundColor Cyan
