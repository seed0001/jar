# JARVIS Standalone App

I have converted JARVIS into a standalone application experience.

## How to use
1. **Desktop Icon**: Look for the **JARVIS** icon on your Desktop. Double-click it to start everything silently.
2. **Window Mode**: The app will open in its own window without browser tabs or address bars.
3. **Background Services**: The backend and frontend run in the background. 

## Files Created
- `assets/icon.ico`: The premium JARVIS icon.
- `scripts/launch_hidden.vbs`: Launches the system without showing command prompts.
- `scripts/start_services.bat`: The logic to start backend, frontend, and the app window.
- `Install_JARVIS.ps1`: Run this if you ever need to recreate the desktop shortcut.

## Troubleshooting
If the app doesn't open, check these log files in the root folder:
- `jarvis_launcher.log`: Main launcher status.
- `backend.log`: Backend server errors.
- `frontend.log`: Frontend server errors.
