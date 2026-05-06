# Project overview

## What this repository is

This is a **local-first AI chat assistant** branded as **J.A.R.** / **J.A.R.V.I.S.** (“Dumbi” lineage in comments). It is not a single compiled binary; it is a **small full-stack app**:

- **Backend**: Python [FastAPI](https://fastapi.tiangolo.com/) (`backend/app/`), talking to **[Ollama](https://ollama.com/)** on your machine for text generation.
- **Frontend**: [React](https://react.dev/) + [Vite](https://vitejs.dev/) (`frontend/`), dark “gem” UI with streaming chat.
- **Data**: SQLite for chat history, JSON files for a user profile and learned “skills,” plus optional trajectory logging for an older evaluation pipeline.

The product goal is a **standalone Windows experience**: double-click launchers start the API and dev server, then open the UI in **Edge or Chrome “app mode”** (no browser chrome).

## Naming drift (read this once)

Several layers use different names (**Jar**, **JARVIS**, **J.A.R.**, **Dumbi-JARVIS**). Treat them as the same product line with inconsistent renames. Root `README.md` is a stub; `README_APP.md` describes the desktop-style launcher story.

## Repository map (source only)

| Path | Role |
|------|------|
| `backend/app/main.py` | FastAPI app: `/chat`, sessions, profile, feedback, static `dist` if present |
| `backend/app/config.py` | Loads `.env`, paths for DB and `skills/` |
| `backend/app/core/` | LLM (Ollama), persona (`jar_brain.py`), web search helper, trajectory logger |
| `backend/app/memory/` | Episodic DB, skills, reflection/skillbank, profile, snippets, context compression |
| `frontend/src/` | React UI: `App.jsx`, `components/*`, styles in `index.css` |
| `skills/` | JSON “SkillRL” heuristics loaded at startup (`*.json`) |
| `scripts/` | Windows launcher batch, VBS “hidden window,” optional Python utilities |
| `models/piper/` | Piper TTS voice **metadata** only (`en_GB-alan-medium.onnx.json`); the matching `.onnx` binary is not in this tree |
| `requirements.txt` | Python dependencies (includes voice/search libs; current backend code path is **text-only**) |
| `.env.example` | Template env vars (some reflect an older multi-tier Qwen setup; live backend uses a **fixed** Ollama model) |
| `BORISLAV_PROFILE.json` | Default / shipped user profile (name, hardware prefs, regions) used for prompt injection |
| `start.bat`, `Install_JAR.ps1` | Quick start and desktop shortcut installer |
| `New Text Document.bat` | Accidental artifact: appends to `README.md` and configures `git remote` — **do not run** |

## External dependencies you must provide

1. **Python 3.10+** with `pip`.
2. **Node.js** and `npm` (for Vite dev server or production build).
3. **[Ollama](https://ollama.com/)** running locally, with the model **`llama2-uncensored`** pulled (`ollama pull llama2-uncensored`). The backend hardcodes this model name.

## Optional / legacy assets

- **`frontend/node_modules/`**: Third-party packages (not authored here; do not treat as project documentation).
- **`scripts/watch_qwen3.py`**: Polls for Qwen3 models; the current `llm.py` does **not** use Qwen tiers anymore.
- **`scripts/skillrl_distill.py`**: Imports `app.core.eval_harness`, which **does not exist** in this repo — the script will fail until that module is added or the import is removed.
- **`frontend/src/components/AuraSphere.jsx`**: Rich canvas visualization for voice/tier states; **nothing imports it** in the current `App.jsx`.

## Content and safety note

The system persona in `backend/app/core/jar_brain.py` is written to **remove normal assistant refusal behavior** and to steer the model toward answering all requests. If you run this stack, you are responsible for **who uses it**, **what model weights you load**, and **compliance with law and policy**. This documentation describes the code as-is, not an endorsement of any use case.

## Where to read next

- **Architecture and APIs**: `docs/02-backend-and-api.md`
- **UI and streaming**: `docs/03-frontend-and-ux.md`
- **Memory, profile, learning loops**: `docs/04-memory-profile-and-learning.md`
- **Install, run, logs, gaps**: `docs/05-setup-operations-and-gaps.md`
