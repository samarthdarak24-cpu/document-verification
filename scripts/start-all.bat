@echo off
REM ---------------------------------------------------------------------------
REM DocuTrace - start backend and frontend in two windows.
REM
REM Usage (from the repository root):
REM     scripts\start-all.bat
REM
REM Each server gets its own console window so you can read its logs and stop it
REM independently with Ctrl+C.
REM ---------------------------------------------------------------------------

setlocal
set "ROOT=%~dp0.."

if not exist "%ROOT%\backend\app\main.py" (
    echo [error] Could not find the backend at "%ROOT%\backend".
    echo         Run this script from the repository root.
    exit /b 1
)
if not exist "%ROOT%\frontend\package.json" (
    echo [error] Could not find the frontend at "%ROOT%\frontend".
    exit /b 1
)

echo Starting DocuTrace...
echo   backend  -^> http://127.0.0.1:8000
echo   frontend -^> http://127.0.0.1:5173
echo.

start "DocuTrace backend" cmd /k "cd /d "%ROOT%\backend" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

REM Give uvicorn a moment to bind before Vite starts proxying to it.
timeout /t 4 /nobreak >nul

start "DocuTrace frontend" cmd /k "cd /d "%ROOT%\frontend" && npm run dev"

echo Both servers launched in separate windows.
echo Open http://127.0.0.1:5173 once the frontend reports "ready".
endlocal
