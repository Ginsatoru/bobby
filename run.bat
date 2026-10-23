@echo off
cd /d "%~dp0"

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -q -r requirements.txt || goto :error

if not exist .env copy .env.example .env >nul

start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
exit /b

:error
echo.
echo Setup failed. Make sure Python 3.10+ is installed and on PATH.
pause
