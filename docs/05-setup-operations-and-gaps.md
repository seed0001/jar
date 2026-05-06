# Setup, operations, and known gaps

## Prerequisites

1. **Python 3.10+** on PATH as `python`.
2. **Node.js** (includes `npm`).
3. **Ollama** installed and running; pull the expected model:

   ```bash
   ollama pull llama2-uncensored
   ```

4. Copy **`.env.example`** to **`.env`** in the repo root and adjust if needed (at minimum confirm `OLLAMA_BASE_URL`).

## Quick start (Windows)

**Option A — `start.bat` (visible steps)**

- Ensures `pip install -r requirements.txt` and `npm install` in `frontend` if needed.
- Starts backend: `uvicorn app.main:app --port 8765` from `backend/`.
- Starts frontend: `npm run dev` from `frontend/`.
- Waits 5 seconds, then opens `http://localhost:5173` in Edge app mode (fallback Chrome, then default browser).

**Option B — Silent / desktop style**

1. Run **`Install_JAR.ps1`** once (PowerShell). It creates a **Desktop shortcut** pointing to `wscript.exe` with `scripts/launch_hidden.vbs`.
2. That VBS runs **`scripts/start_services.bat`** with window style hidden (`0`).
3. Batch file logs to **`jarvis_launcher.log`**, **`backend.log`**, **`frontend.log`** at repo root.

**Installer script mismatch**: `README_APP.md` mentions `Install_JARVIS.ps1` and `assets/icon.ico`; the repo has **`Install_JAR.ps1`** and references **`assets\icon_premium.ico`**. If shortcut creation fails, check that the icon path exists on disk.

## Manual dev (any OS with bash-like steps)

Terminal 1:

```bash
cd backend
pip install -r ../requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8765
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (typically `http://localhost:5173`).

## Production-ish single port

1. `cd frontend && npm run build`
2. Serve **`frontend/dist`** from FastAPI (automatic when `dist` exists — see `main.py` static mount) **or** put behind a reverse proxy.

Note: default `start.bat` still runs **Vite dev** on 5173, not `vite build`.

## Python dependency footprint vs code

`requirements.txt` lists **Whisper, faster-whisper, openwakeword, webrtcvad, pyaudio, pyttsx3**, DuckDuckGo search, etc. Comments in `main.py` and `config.py` state **TTS / vision / voice pipeline removed** from this revision. You still install heavy deps if you follow `requirements.txt` blindly; trimming unused packages is a possible cleanup (not done in docs).

## Data files created at runtime

| Artifact | Description |
|----------|-------------|
| `jar_memory.db` | Chat history, FTS index |
| `trajectories.db` | May remain empty unless trajectory logging is wired |
| `context_profiles.json` | Summaries after long-session compression |
| `skills/skillbank.json` | Learned lessons (starts as `{}` in repo) |
| `BORISLAV_PROFILE.json` | Updated when facts/corrections/heuristics are recorded |
| `*.log` | Launcher / service logs when using `start_services.bat` |

## Git and junk files

- **`New Text Document.bat`**: Contains `echo`, `git init`, `git remote add origin https://github.com/marinovstud-ux/Jar.git`, etc. It is not part of the app runtime. **Remove or ignore** to avoid accidental execution.
- Root **`README.md`**: Stub lines `"# Jar"` — the real narrative is split across `README_APP.md` and these docs.

## Broken or incomplete integrations

| Item | Issue |
|------|--------|
| `multi_hop_search` | Imported in `main.py`, **not used** in `/chat` |
| `scripts/skillrl_distill.py` | Imports **missing** `app.core.eval_harness` |
| `scripts/watch_qwen3.py` | Targets Qwen3 tiers; backend uses **fixed** `llama2-uncensored` |
| `GET/PATCH /schema` | Expects **`BORISLAV_SCHEMA.json`** — may be absent |
| `Install_JAR.ps1` / README | Paths and filenames **disagree** with `README_APP.md` |
| `Sidebar.jsx` timestamps | Uses `updated_at` / `created_at` but API returns **`updated`** |
| `AuraSphere.jsx` | **Unused** component |
| Piper TTS | Only **`en_GB-alan-medium.onnx.json`** present under `models/piper/`; ONNX weights not in tree |

## Security and deployment hygiene

- **CORS is wide open** (`allow_origins=["*"]`).
- **Persona** encourages unrestricted answers; combine with care if exposing to a network.
- **Local SQLite** stores full transcripts; protect filesystem backups accordingly.

## Suggested next steps for a new maintainer

1. Decide whether to **re-enable web search** in `/chat` or **remove** the import and UI quick action.
2. Fix **sidebar date** fields to match API (`updated`).
3. Align **installer script**, icon paths, and `README_APP.md`.
4. Either add **`eval_harness.py`** or delete/fix **`skillrl_distill.py`**.
5. Prune **`requirements.txt`** to match the actually used code path if you want leaner installs.
