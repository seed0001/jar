# Memory, profile, and learning

This project layers several **complementary persistence mechanisms** on top of the raw chat API.

## 1. Episodic memory — SQLite (`jar_memory.db`)

**Module**: `backend/app/memory/episodic.py`  
**Config**: `DB_PATH` in `config.py` (repo root).

### Tables (conceptual)

- **`messages`**: `session`, `role`, `content`, `ts`, optional `power_level`, `cognitive_mode`, `compressed` flag.
- **`sessions`**: session id, `title`, `summary`, `created`, `updated`.
- **`messages_fts`**: FTS5 virtual table mirroring message content for search.
- **`found_facts`**: structured facts (helper `save_fact` exists).

### Operations used by `/chat`

- **`save_message`** after user and assistant turns.
- **`get_buffer`**: last `BUFFER_LIMIT` non-compressed messages for the session (roles for OpenAI-style history).
- **`search_memory`**: FTS match with fallback to SQL `LIKE`.
- **`get_buffer_full`**: full transcript for sidebar reload.
- **`compress_old_messages`**: when a session grows past `COMPRESS_AFTER_TURNS` (40), older messages (except `KEEP_RECENT` 20) can be zlib-compressed in place (`compressed=1`). Decompression helpers exist but chat retrieval filters `compressed=0` for recent buffer — understand this before relying on long-thread verbatim recall.

### Session titles

After assistant reply, if buffer length ≤ 4, first user words become `sessions.title`.

## 2. Knowledge snippets — cross-session keywords

**Module**: `knowledge_snippets.py` → `get_recent_context(session_id, query)`

Pulls up to a few **recent messages from other sessions** whose text contains keywords from the current query (simple `LIKE`, not embeddings). Injected as a system block in `/chat`.

## 3. Context profiles — long-session summarization

**Module**: `context_manager.py`  
**File**: `context_profiles.json` at repo root.

When a session has **more than 20** messages, `maybe_compress_session`:

1. Takes the **older** portion of the thread.
2. Calls **`llm.chat`** to summarize into bullet points.
3. Saves summary keyed by `session_id` in `context_profiles.json`.
4. **Deletes** the summarized rows from `messages` (keeps only recent high-fidelity tail in DB).

`get_context_profile` injects that summary as a system message so the model retains coarse history after DB trim.

## 4. User profile — JSON on disk

**Module**: `profile.py`  
**File**: `BORISLAV_PROFILE.json` (shipped example targets a specific user template).

Contains:

- `user` (name, preferred_address, location, timezone)
- `hardware` (CPU, RAM, inference engine, quantization, thermal limit)
- `preferences` (language, coding style, regions)
- Arrays: `projects`, `learned_facts`, `corrections`, optional `adaptive_heuristics` (added by reflection)

**`update_profile_from_message`**: regex-based fact extraction from user text (preferences, projects, identity, etc.).  
**`record_correction`**: appends to `corrections` when `/chat` detects correction keywords.

**`get_profile_context`**: formats a concise block for the system prompt (name, location, hardware, recent facts/projects).

To personalize for yourself, edit or replace `BORISLAV_PROFILE.json` and adjust `.env` comments if desired.

## 5. Skill files — `skills/*.json`

**Module**: `skills.py`

Each JSON file is expected to look like `greeting_protocol.json`:

```json
{
  "skill_name": "...",
  "version": "1.0.0",
  "heuristic": "Natural language rule...",
  "origin": "system_default | user_manual | ..."
}
```

All matching files are loaded at startup; `get_skill_context()` joins them into a markdown list for the system prompt. `POST /skills` appends new files.

## 6. Skillbank — `skills/skillbank.json`

**Module**: `reflection.py`

In-memory dict `_skillbank`, persisted as JSON object (keys → lesson records).

Population sources:

- **`immediate_reflect`**: after each reply (async), a **small follow-up LLM call** asks for 0–2 JSON “lessons”; results merge into skillbank; adaptive heuristics may also update `BORISLAV_PROFILE.json`.
- **`record_feedback`**: thumbs up/down from UI writes preference/frustration entries.

`get_skillbank_context()` injects the last dozen-ish lessons as a system block.

## 7. SkillRL scheduling — nightly distillation

**Module**: `knowledge_snippets.py` → `schedule_skillrl()`

Starts a **daemon thread** running an asyncio loop that sleeps until **03:00 UTC+3** (hardcoded offset, not full timezone library), then runs `run_skillrl_distillation()`:

- Scans recent user messages for correction regexes.
- For each hit, calls `save_skill(...)` with a slug derived from message text — can create **many** skill files over time.

Also calls `summarize_old_sessions()` to fill `sessions.summary` for stale sessions.

**Caveat**: the “next 03:00” calculation uses `target.replace(day=target.day + 1)` which is **not calendar-safe** at month boundaries (Python `datetime.replace` does not roll months automatically). Edge-case bug.

## 8. Trajectory DB and offline distillation script

- **`trajectory_logger.py`**: SQLite `trajectories.db` for rich traces (GVU, PRISM, etc.). **Not written by current `/chat`.**
- **`scripts/skillrl_distill.py`**: Intended to read failure trajectories and eval harness; depends on **missing** `app.core.eval_harness` — treat as **non-functional** unless you restore that module from elsewhere.

## 9. `PATCH /schema` and `BORISLAV_SCHEMA.json`

`main.py` documents a separate JSON schema file for structured user attributes. It is **not** included in the repository snapshot reviewed; the endpoint returns an error object if missing.
