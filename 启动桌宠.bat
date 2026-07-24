@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Moepet] First run: creating the application environment...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
    if errorlevel 1 (
        echo.
        echo [Moepet] Setup failed. Install Python 3.11, then run setup.ps1 again.
        pause
        exit /b 1
    )
)

start "Moepet" /b ".venv\Scripts\python.exe" "%~dp0main.py"
endlocal
