# Backend and HTTP API

## Stack

- **Framework**: FastAPI (`backend/app/main.py`).
- **Server**: Uvicorn (invoked from `start.bat` / `scripts/start_services.bat` as `python -m uvicorn app.main:app --port 8765`).
- **LLM**: Ollama HTTP API (`app/core/llm.py`), model fixed to **`llama2-uncensored`**, base URL from `OLLAMA_BASE_URL` (default `http://localhost:11434`).

## Configuration (`app/config.py`)

- Loads `.env` from the **repository root** (same folder as `requirements.txt`).
- Defines:
  - `DB_PATH` → `jar_memory.db` at repo root
  - `SKILLS_DIR` → `skills/`
  - `BUFFER_LIMIT`, `CONTEXT_PROFILES` from env (defaults 20 and 5)
  - `CPU_THROTTLE_PCT` (default 85) — referenced historically; the v6 chat path does not implement dynamic model tier switching in code reviewed here.

## Startup sequence (`main.py` → `@app.on_event("startup")`)

On boot the server:

1. `await init_db()` — SQLite schema for messages, sessions, FTS index, facts.
2. `load_skills()` — all `skills/*.json` into memory for prompt injection.
3. `load_profile()` — `BORISLAV_PROFILE.json` (creates default if missing).
4. `load_skillbank()` — `skills/skillbank.json` preference lessons.
5. `llm.check_availability()` — probes Ollama `/api/tags`.
6. `schedule_skillrl()` — background thread for nightly distillation (see memory doc).
7. `asyncio.create_task(periodic_flush_task(...))` — WAL checkpoint every 300s.

## Main chat pipeline: `POST /chat`

Request JSON:

- `query` (string, required): user message.
- `session_id` (string, optional): UUID; generated if omitted.

Response: **Server-Sent Events** (`text/event-stream`). Each event is a line `data: {json}`.

Event types emitted:

| `type` | Payload | Meaning |
|--------|---------|---------|
| `state` | `{ "state": "thinking" \| "responding" }` | UI status |
| `token` | `{ "token": "..." }` | streamed assistant text |
| `done` | `{ "session_id", "model_used" }` | stream finished |

**Order of operations (simplified):**

1. Optional correction handling: keywords like “no jar”, “incorrect” → `record_correction`; always `update_profile_from_message` for fact regexes.
2. Save user message to SQLite.
3. Retrieve **episodic** snippets (`search_memory`), **cross-session** keyword snippets (`get_recent_context`), **context profile** summary if present (`get_context_profile`), **skill files** (`get_skill_context`), **skillbank** (`get_skillbank_context`).
4. Build `messages` list: system prompt from `build_system_prompt()` in `jar_brain.py`, then the above blocks, then last **10** turns from `get_buffer`, then the new user message.
5. Stream tokens from `llm.stream_chat`.
6. Save assistant message; maybe set session title from first user words; fire-and-forget `immediate_reflect`, `maybe_compress_session`, `compress_old_messages`.
7. Emit `done`.

**Not wired in this handler:** `multi_hop_search` from `app/core/web_search.py` is **imported** in `main.py` but **never called** in `/chat`. The UI still advertises “web research” in quick prompts; unless another route uses search, **no DuckDuckGo results are injected** in the current flow.

## Other endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Status, Ollama flag, `llm.model`, hardware snapshot from `get_hardware_state()` |
| GET | `/sessions` | List sessions (id, title, summary, updated) |
| GET | `/sessions/{id}/messages` | Full message list for one session |
| DELETE | `/sessions/{id}` | Delete one session |
| DELETE | `/sessions` | Clear all history |
| GET | `/memory/search?q=` | FTS / LIKE memory search |
| GET | `/profile` | Raw `BORISLAV_PROFILE.json` |
| GET | `/schema` | Reads `BORISLAV_SCHEMA.json` from repo root (**file may be absent**; then JSON error) |
| PATCH | `/schema` | Merge-update that schema file |
| POST | `/feedback` | Thumbs up/down → `record_feedback` |
| GET | `/skillbank` | Last 20 skillbank entries (internal dict) |
| POST | `/skills` | Save named heuristic JSON into `skills/` |
| GET | `/greeting` | `format_jar_greeting()` string |

## Static frontend (packaged mode)

If `frontend/dist` exists relative to the app root, FastAPI mounts **StaticFiles** at `/` to serve the built SPA. In normal dev mode you typically run Vite on port **5173** and FastAPI on **8765** separately (`start.bat` does exactly that).

## Persona and system prompt (`jar_brain.py`)

- Builds a long **JAR_PERSONA** string (also aliased `JARVIS_PERSONA`).
- Injects **profile** context from `get_profile_context()`, **Sofia time**, optional **hardware alerts** (CPU high, battery low, thermal), and **skills** string.

## LLM details (`llm.py`)

- Uses aiohttp for streaming POST to `/api/chat`.
- Windows-oriented Ollama options: `num_ctx` 2048, `num_thread` 8, `keep_alive` 10m, etc.
- Sync `chat()` used by reflection and context summarization helpers.

## Trajectory logger (`trajectory_logger.py`)

- Writes to `trajectories.db` at repo root (path uses `parent.parent.parent.parent` from `app/core` — effectively repo root).
- Schema includes GVU / PRISM style fields from an older agent architecture. **Nothing in `main.py` calls `log_trajectory`** in the reviewed code, so this DB may stay empty unless other code paths or scripts use it.

## CORS

`CORSMiddleware` allows all origins — convenient for local dev; tighten if exposed beyond localhost.
