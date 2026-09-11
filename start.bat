@echo off
chcp 65001 >nul
REM 智能车间设备故障诊断与预测性维护系统 - 一键启动
cd /d "%~dp0backend"

REM 若已运行则直接打开浏览器
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo 系统已在运行: http://localhost:8000
    start "" http://localhost:8000
    goto :end
)

echo ============================================
echo  智能车间设备故障诊断与预测性维护系统
echo  Web UI:   http://localhost:8000
echo  API Docs: http://localhost:8000/docs
echo  （首次运行请先执行 scripts/seed_all.py 初始化数据）
echo ============================================
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv 虚拟环境，请先运行 setup.bat
    goto :end
)
set PYTHONIOENCODING=utf-8
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
:end
pause
