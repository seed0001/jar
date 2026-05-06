@echo off
setlocal enabledelayedexpansion
title J.A.R.V.I.S. Launcher

:: Root directory
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo  ============================================================
echo     J.A.R.V.I.S. - Standalone App Mode
echo  ============================================================
echo.

:: 1. Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+.
    pause & exit /b 1
)

:: 2. Check Node/NPM
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] NPM not found. Please install Node.js.
    pause & exit /b 1
)

:: 3. Install/Update dependencies (Silent)
echo [1/3] Preparing systems...
pip install -q -r requirements.txt
cd frontend
if not exist "node_modules" (
    echo [1/3] Installing frontend packages (this may take a minute)...
    call npm install --silent
)
cd ..

:: 4. Launch Servers
echo [2/3] Launching Backend ^& Frontend...
start /b "JARVIS_Backend" cmd /c "cd backend && python -m uvicorn app.main:app --port 8765"
start /b "JARVIS_Frontend" cmd /c "cd frontend && npm run dev"

:: 5. Wait and Open App Window
echo [3/3] Opening JARVIS Window...
timeout /t 5 /nobreak >nul

set "URL=http://localhost:5173"
:: Try to open in App Mode (Edge or Chrome)
start "" msedge --app=%URL%
if errorlevel 1 (
    start "" chrome --app=%URL%
    if errorlevel 1 (
        start %URL%
    )
)

echo.
echo  ============================================================
echo     JARVIS is now running in standalone window mode.
echo     Close the JARVIS window to finish your session.
echo  ============================================================
echo.
pause
