@echo off
setlocal enabledelayedexpansion

:: Get the root directory (one level up from scripts)
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%.."
set "ROOT_DIR=%cd%"

echo [%DATE% %TIME%] Starting JARVIS services... >> "%ROOT_DIR%\jarvis_launcher.log"

:: Check if Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH >> "%ROOT_DIR%\jarvis_launcher.log"
    exit /b 1
)

:: Start Backend in background
echo Starting Backend... >> "%ROOT_DIR%\jarvis_launcher.log"
start /b "JARVIS_Backend" cmd /c "cd /d "%ROOT_DIR%\backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 >> "%ROOT_DIR%\backend.log" 2>&1"

:: Start Frontend in background
echo Starting Frontend... >> "%ROOT_DIR%\jarvis_launcher.log"
start /b "JARVIS_Frontend" cmd /c "cd /d "%ROOT_DIR%\frontend" && npm run dev >> "%ROOT_DIR%\frontend.log" 2>&1"

:: Wait for services to initialize
timeout /t 6 /nobreak >nul

:: Launch the App Window
echo Launching App Window... >> "%ROOT_DIR%\jarvis_launcher.log"

:: Try Edge first, then Chrome, then default browser
set "APP_URL=http://localhost:5173"
start "" msedge --app=%APP_URL%
if errorlevel 1 (
    start "" chrome --app=%APP_URL%
    if errorlevel 1 (
        start %APP_URL%
    )
)

echo [%DATE% %TIME%] JARVIS successfully launched. >> "%ROOT_DIR%\jarvis_launcher.log"
exit /b 0
