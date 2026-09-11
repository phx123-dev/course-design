@echo off
chcp 65001 >nul
REM 故障分类模型训练（全量）。快速版: train.bat quick
cd /d "%~dp0backend"
set PYTHONIOENCODING=utf-8
if "%1"=="quick" (
    "..\.venv\Scripts\python.exe" scripts\train_models.py --quick
) else (
    "..\.venv\Scripts\python.exe" scripts\train_models.py
)
pause
