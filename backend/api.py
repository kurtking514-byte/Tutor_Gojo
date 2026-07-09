"""
api.py - FastAPI server for Tutor Gojo's backend.

This is the new entry point for chat/database operations, replacing the
orchestration that used to live inside main.py's Flet UI callbacks. It
exposes:

    POST /chat       - send a user message, stream the assistant's reply
    GET  /history     - list sessions, or get one session's messages
    POST /session     - create a new chat session
    GET  /progress    - learning progress stats

Run with:  uvicorn api:app --reload   (from inside backend/)
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import config
import database
import obsidian_backend
import llm_router
from services import chat_service, history_service, lesson_recommender, memory_service

app = FastAPI(title="Tutor Gojo API")

# Allow the React dev server (and a packaged frontend) to call this API.
# Tighten allow_origins to your actual frontend URL(s) before shipping.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "https://tutor-gojo-frontend.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Initialize the SQLite schema on server start, same as the old
    Flet app did on launch. Also initializes the educational memory
    tables (memory_database.py) alongside the existing chat/session
    schema - both run once, at startup, so the memory tables exist
    before any request can reach them."""
    database.init_database()
    obsidian_backend.VAULT_PATH = config.get_vault_path()
    memory_service.initialize_memory_backend()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str
    message: str
    use_search: bool = False


class SessionRequest(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/chat")
def chat(req: ChatRequest):
    """Stream the assistant's reply for a user message via Server-Sent
    Events. The frontend should consume this with EventSource (or an
    SSE-aware fetch wrapper, since EventSource itself only supports GET).
    Each event's `data` field is a raw text chunk; a final `event: done`
    marks completion.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    def event_stream():
        try:
            for chunk in chat_service.stream_chat(req.session_id, req.message):
                # SSE wire format: each line prefixed "data: ", blank line ends the event.
                # Newlines inside a chunk must each get their own "data: " prefix.
                safe_chunk = chunk.replace("\n", "\ndata: ")
                yield f"data: {safe_chunk}\n\n"
            yield "event: done\ndata: [DONE]\n\n"
        except (ValueError, RuntimeError) as e:
            # Friendly errors raised by gemini_client (bad API key, etc.) or
            # llm_router when all providers fail over (RuntimeError).
            safe_err = str(e).replace("\n", " ")
            yield f"event: error\ndata: {safe_err}\n\n"
        except Exception as e:
            # Catch-all so an unexpected failure still ends the SSE stream
            # cleanly instead of crashing the response mid-stream.
            safe_err = str(e).replace("\n", " ")
            yield f"event: error\ndata: {safe_err}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/history")
def history(session_id: Optional[str] = Query(default=None), limit: int = 50):
    """If session_id is given, return that session's messages.
    Otherwise, return the list of all sessions."""
    if session_id:
        return {"session_id": session_id, "messages": history_service.get_messages(session_id, limit=limit)}
    return {"sessions": history_service.list_sessions()}


@app.post("/session")
def create_session(req: SessionRequest):
    """Create a new chat session and return its id."""
    session_id = chat_service.create_session(title=req.title, topic=req.topic)
    return {"session_id": session_id}


@app.get("/progress")
def progress(topic: Optional[str] = Query(default=None)):
    """Return learning progress, optionally filtered to one topic."""
    return {"progress": history_service.get_progress(topic=topic), "stats": history_service.get_stats()}


@app.get("/memory")
def memory():
    """Read-only view of the student's full educational memory context.
    Returns exactly what memory_service.get_memory_context() produces -
    no reshaping, filtering, or computation here; the frontend decides
    how to render the 13 categories bundled inside it."""
    try:
        return {"memory": memory_service.get_memory_context()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve memory: {e}")


@app.get("/lesson-recommendation")
def lesson_recommendation():
    """Read-only lesson recommendation derived from the student's
    educational memory. Fetches memory_context via
    memory_service.get_memory_context(), then hands it to
    lesson_recommender.build_lesson_recommendation() - no reshaping,
    filtering, or computation here; the recommendation dict is returned
    exactly as produced, same pattern as /memory."""
    try:
        memory_context = memory_service.get_memory_context()
        recommendation = lesson_recommender.build_lesson_recommendation(memory_context)
        return {"recommendation": recommendation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build lesson recommendation: {e}")


@app.get("/health")
def health():
    """Basic liveness check for the frontend/dev tooling."""
    return {"status": "ok"}


@app.get("/diagnostics/providers")
def diagnostics_providers():
    """Phase 7A (Observability, ROADMAP.md): read-only snapshot of
    per-provider health/latency bookkeeping already collected by
    llm_router's ProviderHealthRegistry (Phase 10A/10D). Does not
    trigger any provider calls, does not affect routing/failover, and
    exposes no API keys or credentials - see
    llm_router.get_diagnostics() for the exact shape returned.
    """
    return llm_router.get_diagnostics()


@app.get("/diagnostics/memory")
def diagnostics_memory():
    """Phase 7B (Observability, ROADMAP.md): read-only snapshot of the
    most recently completed memory-pipeline execution, already
    collected by chat_service._get_memory_prompt(). Does not run the
    memory pipeline itself, does not affect retrieval/ranking, and
    exposes no conversation text, prompt content, or memory-category
    content - see chat_service.get_memory_diagnostics() for the exact
    shape returned.
    """
    return chat_service.get_memory_diagnostics()
