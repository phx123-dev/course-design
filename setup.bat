@echo off
chcp 65001 >nul
REM 首次运行：创建 Python 3.13 虚拟环境 + 安装依赖 + 初始化数据
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境 (Python 3.13)...
    py -3.13 -m venv .venv
)
echo [2/3] 安装依赖（清华镜像）...
".venv\Scripts\pip.exe" install -r backend\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [3/3] 初始化数据库与模拟数据（含快速模型训练，约 1 分钟）...
cd backend
set PYTHONIOENCODING=utf-8
"..\.venv\Scripts\python.exe" scripts\seed_all.py --quick
cd ..

echo.
echo 初始化完成！运行 start.bat 启动系统。
pause
