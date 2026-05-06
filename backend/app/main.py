"""
JAR — FastAPI Backend (Ollama, three-tier model map, SSE chat + Edge TTS).
"""
import json
import os
import uuid
import logging
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from app.config import (
    TIER_MODELS_PATH,
    EDGE_TTS_DEFAULT_VOICE,
    JAR_INJECT_WINSTATE_EACH_CHAT,
)
from app.core import edge_tts as edge_tts_module
from app.core import stt_whisper as stt_whisper_module
from app.core.llm import llm
from app.core.jar_brain import build_system_prompt, format_jar_greeting, get_hardware_state
from app.core.tier_select import auto_select_tier
from app.core.local_tools import allowed_read_roots
from app.core.system_shell import system_shell_enabled
from app.core.tool_router import plan_tools, execute_tool_plan
from app.core.web_search import web_search_available
from app.memory.episodic import (
    init_db, save_message, get_buffer, get_buffer_full, search_memory,
    get_sessions, update_session_title, delete_session_db, clear_all_history,
    compress_old_messages, periodic_flush_task,
)
from app.memory.skills import load_skills, save_skill
from app.memory.knowledge_snippets import get_recent_context, schedule_skillrl
from app.memory.reflection import immediate_reflect, record_feedback, get_skillbank_context, load_skillbank
from app.memory.context_manager import maybe_compress_session, get_context_profile
from app.memory.profile import (
    load_profile, update_profile_from_message,
    record_correction, get_profile_context, get_user_name,
)

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("JAR.API")

app = FastAPI(title="J.A.R. Backend", version="6.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CORRECTION_KEYWORDS = ["no jar", "that's wrong", "incorrect", "i prefer", "not right", "actually", "wrong"]


@app.on_event("startup")
async def startup():
    await init_db()
    load_skills()
    load_profile()
    load_skillbank()
    llm.check_availability()
    schedule_skillrl()
    asyncio.create_task(periodic_flush_task(interval_seconds=300))
    tm = llm.tier_models
    edge_ok = edge_tts_module.EDGE_TTS_AVAILABLE
    stt_ok = stt_whisper_module.stt_import_ok()
    shell_ok = system_shell_enabled()
    logger.info(
        f"✧ J.A.R. v6 online → tiers: 1={tm.get(1)} | 2={tm.get(2)} | 3={tm.get(3)} "
        f"| edge-tts={edge_ok} | stt={stt_ok} | system_shell={shell_ok}"
    )


@app.get("/health")
async def health():
    hw = get_hardware_state()
    tm = llm.tier_models
    return {
        "status": "online",
        "ollama": llm.is_available,
        "model": llm.model,
        "tier_models": {str(k): tm[k] for k in (1, 2, 3)},
        "edge_tts": edge_tts_module.EDGE_TTS_AVAILABLE,
        "edge_tts_default_voice": EDGE_TTS_DEFAULT_VOICE,
        "web_search": web_search_available(),
        "jar_file_read_roots": len(allowed_read_roots()),
        "stt": stt_whisper_module.stt_import_ok(),
        "jar_system_shell": system_shell_enabled(),
        "jar_inject_winstate_each_chat": JAR_INJECT_WINSTATE_EACH_CHAT,
        **hw,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/models/tiers")
async def get_models_tiers():
    """Ollama tag list + tier→model map (for configuring which models back each tier)."""
    llm.check_availability()
    tm = llm.tier_models
    return {
        "tier_models": {str(k): tm[k] for k in (1, 2, 3)},
        "ollama_models": llm.available_models,
    }


@app.post("/models/tiers")
async def post_models_tiers(payload: dict = Body(...)):
    """Persist the three tier models to jar_tier_models.json and reload."""
    raw = payload.get("tier_models") if isinstance(payload.get("tier_models"), dict) else payload
    new_t = {}
    for k in (1, 2, 3):
        sk = str(k)
        v = raw.get(sk) if isinstance(raw, dict) else None
        if v is None and isinstance(raw, dict):
            v = raw.get(k)
        if not v or not str(v).strip():
            return JSONResponse(
                {"error": f"Tier {k} requires a non-empty model name (Ollama tag)."},
                status_code=400,
            )
        new_t[k] = str(v).strip()

    TIER_MODELS_PATH.write_text(
        json.dumps({"1": new_t[1], "2": new_t[2], "3": new_t[3]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    llm.reload_tier_models()
    llm.check_availability()
    return {"status": "saved", "tier_models": {str(k): new_t[k] for k in new_t}}


@app.post("/chat")
async def chat(payload: dict = Body(...)):
    query      = payload.get("query", "").strip()
    session_id = payload.get("session_id", str(uuid.uuid4()))

    if not query:
        return JSONResponse({"error": "Query required"}, status_code=400)
    if not llm.is_available:
        llm.check_availability()

    hw = get_hardware_state()
    tier = auto_select_tier(query, hw)

    logger.info(
        f"--- Chat Request Received: {query[:50]}... (Session: {session_id}, auto_tier={tier}) ---"
    )

    # Auto-record corrections / profile updates
    if any(kw in query.lower() for kw in CORRECTION_KEYWORDS):
        record_correction(query)
    update_profile_from_message(query)

    async def event_generator():
        logger.info(f"Event generator started for session {session_id}")
        yield f"data: {json.dumps({'type': 'state', 'state': 'thinking'})}\n\n"
        yield f"data: {json.dumps({'type': 'meta', 'tier': tier, 'model': llm.get_model_for_tier(tier)})}\n\n"
        await save_message(session_id, "user", query, power_level=tier)
        logger.info(f"Message saved to DB for session {session_id}")

        # ── Memory retrieval ──────────────────────────────────────────────────
        memory_snippets, snippet_ctx = [], ""
        try:
            memory_snippets = await search_memory(query, limit=3)
            snippet_ctx     = await get_recent_context(session_id, query)
        except Exception as e:
            logger.warning(f"Memory error: {e}")

        # ── Local tools (web / files / system) ────────────────────────────────
        tool_plan = plan_tools(query)
        tool_blocks: list = []
        tools_meta: dict = {}
        web_search_started = bool(tool_plan.web_queries and web_search_available())
        if web_search_started:
            yield f"data: {json.dumps({'type': 'tools', 'searching_text': 'Searching with DuckDuckGo…'})}\n\n"
        try:
            tool_blocks, tools_meta = await execute_tool_plan(tool_plan)
        except Exception as e:
            logger.exception("Tool plan execution failed: %s", e)
            tool_blocks = [f"### Tool runner failure\n{e}\n"]
            tools_meta = {}
        if web_search_started:
            yield f"data: {json.dumps({'type': 'tools', 'searching_text': None, **tools_meta})}\n\n"
        elif any(
            [
                tools_meta.get("web_searched"),
                tools_meta.get("files_read"),
                tools_meta.get("processes"),
                tools_meta.get("sysinfo"),
                tools_meta.get("winstate"),
                tools_meta.get("shell_ran", 0) > 0,
            ]
        ):
            yield f"data: {json.dumps({'type': 'tools', **tools_meta})}\n\n"

        # ── Build messages ────────────────────────────────────────────────────
        sys_prompt = build_system_prompt(power_level=tier, hw=hw)
        messages = [{"role": "system", "content": sys_prompt}]

        if memory_snippets:
            messages.append({"role": "system", "content": "## Episodic Memory\n" + "\n".join(memory_snippets)})
        if snippet_ctx:
            messages.append({"role": "system", "content": snippet_ctx})

        # Context Profile (compressed older messages)
        ctx_profile = get_context_profile(session_id)
        if ctx_profile:
            messages.append({"role": "system", "content": ctx_profile})

        # Active skills
        from app.memory.skills import get_skill_context as get_skills_inline
        active_skills = get_skills_inline()
        if active_skills:
            messages.append({"role": "system", "content": active_skills})

        # Skillbank
        skillbank_ctx = get_skillbank_context()
        if skillbank_ctx:
            messages.append({"role": "system", "content": skillbank_ctx})

        history = await get_buffer(session_id)
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": query})
        if tool_blocks:
            joined = "\n\n---\n\n".join(tool_blocks)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "[Automated tool results — local file read, DuckDuckGo web search, "
                        "and/or system diagnostics. Use faithfully in your answer, Sir.]\n\n"
                        + joined
                    ),
                }
            )

        # ── Stream response ───────────────────────────────────────────────────
        yield f"data: {json.dumps({'type': 'state', 'state': 'responding'})}\n\n"
        full_response = ""

        try:
            async for token in llm.stream_chat(
                messages,
                tier=tier,
                max_tokens=2048,
                temperature=0.7,
            ):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"FATAL Generator Error: {e}", exc_info=True)
            err = f"\n\n*I do beg your pardon, Sir — something went awry. ({str(e)[:80]})*"
            full_response += err
            yield f"data: {json.dumps({'type': 'token', 'token': err})}\n\n"

        # ── Persist ───────────────────────────────────────────────────────────
        await save_message(session_id, "assistant", full_response, power_level=tier)
        buf = await get_buffer(session_id)
        if len(buf) <= 4:
            title_words = [w for w in query.split() if len(w) > 2][:8]
            smart_title = " ".join(title_words)[:52] or query[:52]
            await update_session_title(session_id, smart_title)

        asyncio.create_task(immediate_reflect(query, full_response))
        asyncio.create_task(maybe_compress_session(session_id))
        asyncio.create_task(compress_old_messages(session_id))

        used_model = llm.get_model_for_tier(tier)
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'model_used': used_model, 'tier': tier})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions")
async def sessions():
    return await get_sessions()

@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    return await get_buffer_full(session_id)

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    await delete_session_db(session_id)
    return {"status": "deleted"}

@app.delete("/sessions")
async def clear_all_sessions():
    await clear_all_history()
    return {"status": "cleared"}

@app.get("/memory/search")
async def memory_search(q: str):
    return {"results": await search_memory(q, limit=10)}

@app.get("/profile")
async def get_profile():
    return load_profile()

@app.get("/schema")
async def get_schema():
    schema_path = Path(__file__).parent.parent.parent / "BORISLAV_SCHEMA.json"
    try:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception:
        return {"error": f"Schema not found at {schema_path}"}

@app.patch("/schema")
async def update_schema(payload: dict = Body(...)):
    schema_path = Path(__file__).parent.parent.parent / "BORISLAV_SCHEMA.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for key, value in payload.items():
            if key in schema and isinstance(schema[key], list) and isinstance(value, list):
                schema[key] = list(set(schema[key] + value))
            else:
                schema[key] = value
        schema["last_updated"] = datetime.utcnow().isoformat() + "Z"
        schema_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"status": "updated"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/feedback")
async def feedback(payload: dict = Body(...)):
    query    = payload.get("query", "")[:200]
    response = payload.get("response", "")[:400]
    rating   = int(payload.get("rating", 0))
    if rating not in (1, -1):
        return JSONResponse({"error": "rating must be 1 or -1"}, status_code=400)
    record_feedback(query, response, rating)
    return {"status": "recorded", "label": "👍" if rating == 1 else "👎"}

@app.get("/skillbank")
async def get_skillbank():
    from app.memory.reflection import _skillbank
    return {"count": len(_skillbank), "entries": dict(list(_skillbank.items())[-20:])}

@app.post("/skills")
async def add_skill(payload: dict = Body(...)):
    name, heuristic = payload.get("name", ""), payload.get("heuristic", "")
    if name and heuristic:
        save_skill(name, heuristic, "user_manual")
        return {"status": "saved"}
    return JSONResponse({"error": "name and heuristic required"}, status_code=400)

@app.get("/greeting")
async def greeting():
    return {"message": format_jar_greeting()}


@app.get("/voice/edge/voices")
async def edge_voice_list():
    """List Microsoft Edge neural voices for the UI (requires `pip install edge-tts`)."""
    if not edge_tts_module.EDGE_TTS_AVAILABLE:
        return JSONResponse(
            {
                "error": "edge-tts is not installed",
                "voices": [],
                "default_voice": EDGE_TTS_DEFAULT_VOICE,
            },
            status_code=503,
        )
    try:
        voices = await edge_tts_module.list_edge_voices()
        return {
            "voices": voices,
            "default_voice": EDGE_TTS_DEFAULT_VOICE,
            "count": len(voices),
        }
    except Exception as e:
        logger.exception("Edge TTS voice list failed: %s", e)
        return JSONResponse({"error": str(e), "voices": [], "default_voice": EDGE_TTS_DEFAULT_VOICE}, status_code=502)


@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)):
    """
    Speech-to-text via faster-whisper (local). Send audio as multipart field `file`
    (e.g. audio/webm from MediaRecorder). Requires `faster-whisper` and ffmpeg for most codecs.
    """
    if not stt_whisper_module.stt_import_ok():
        return JSONResponse(
            {"error": "faster-whisper is not installed", "text": ""},
            status_code=503,
        )
    raw_name = (file.filename or "recording.webm").lower()
    suffix = Path(raw_name).suffix.lower()
    if suffix not in (".webm", ".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".mp4"):
        suffix = ".webm"
    try:
        content = await file.read()
    except Exception as e:
        return JSONResponse({"error": str(e), "text": ""}, status_code=400)
    if not content:
        return JSONResponse({"error": "empty upload", "text": ""}, status_code=400)
    max_bytes = 25 * 1024 * 1024
    if len(content) > max_bytes:
        return JSONResponse({"error": "audio exceeds 25MB", "text": ""}, status_code=400)

    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as out:
            out.write(content)
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            None,
            lambda: stt_whisper_module.transcribe_file(Path(tmp_path)),
        )
        return {"text": text or ""}
    except Exception as e:
        logger.exception("Transcription failed: %s", e)
        return JSONResponse({"error": str(e), "text": ""}, status_code=500)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@app.post("/voice/edge/speak")
async def edge_speak(payload: dict = Body(...)):
    """Synthesize text to MP3 using Edge TTS (body: { text, voice? })."""
    if not edge_tts_module.EDGE_TTS_AVAILABLE:
        return JSONResponse({"error": "edge-tts is not installed"}, status_code=503)
    text = (payload.get("text") or "").strip()
    voice = (payload.get("voice") or EDGE_TTS_DEFAULT_VOICE).strip()
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    if len(text) > 50000:
        return JSONResponse({"error": "text exceeds 50000 characters"}, status_code=400)

    async def audio_stream():
        try:
            async for chunk in edge_tts_module.stream_edge_mp3(text, voice):
                yield chunk
        except Exception as e:
            logger.exception("Edge TTS synthesis failed: %s", e)
            raise

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


# ── Static frontend (production build) ───────────────────────────────────────
import sys
_base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent.parent
_frontend = _base / "frontend" / "dist"
if _frontend.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8765, reload=True)
