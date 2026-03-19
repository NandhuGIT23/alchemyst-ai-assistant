"""
main.py
-------
FastAPI gateway for the chatbot widget.

Endpoints:
  POST /chat          — main chat endpoint (streaming SSE)
  POST /chat/sync     — non-streaming fallback
  DELETE /session     — clear conversation history
  GET  /health        — health check

Flow per message:
  1. Load session history (in-memory)
  2. Classify intent via Claude
  3. Route to correct handler
  4. Stream response back
"""

import uuid
import json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from intent import classify_intent
from handlers import handle_qa, handle_schedule, handle_ticket, handle_escalate
from session import get_history, add_to_history, clear_history, get_active_intent, get_handler_state
from rag_pipeline.embedder import embed_query
from escalation_handler   import handle_escalate
from escalation_detector  import should_escalate

from rag_pipeline.db       import search
from rag_pipeline.config   import TOP_K

app = FastAPI(title="Chatbot API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat_stream(request: Request):
    body       = await request.json()
    question   = body.get("question", "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)

    history = get_history(session_id)

    async def event_stream():
        full_answer = ""
        sources     = []

        try:
            # ── 1. Check if an existing multi-turn flow is in progress ────────
            # If user is mid-flow (e.g. step 2 of scheduling), continue that
            # flow and skip all detection/classification.
            active_intent = _get_active_flow(session_id)
            if active_intent:
                intent = active_intent
                yield _sse("intent", {"intent": intent})
                async for chunk in _run_handler(
                    intent, question, history, session_id, reason=""
                ):
                    if isinstance(chunk, str):
                        full_answer += chunk
                        yield _sse("token", {"text": chunk})
                    elif isinstance(chunk, dict) and "sources" in chunk:
                        sources = chunk["sources"]

                yield _sse("done", {
                    "session_id": session_id,
                    "intent":     intent,
                    "sources":    sources,
                })
                add_to_history(session_id, "user",      question)
                add_to_history(session_id, "assistant", full_answer)
                return

            # ── 2. Pre-retrieval escalation triggers (1, 2, 3) ───────────────
            escalate, reason = await should_escalate(question, history)

            if not escalate:
                # ── 3. Intent classification ──────────────────────────────────
                intent = await classify_intent(question, history)

                # ── 4. Post-retrieval low-confidence check (trigger 4) ────────
                if intent == "qa":
                    rag_scores = _get_rag_scores(question)
                    escalate, reason = await should_escalate(
                        question, history, rag_scores=rag_scores
                    )
                    if escalate:
                        intent = "escalate"
            else:
                intent = "escalate"

            yield _sse("intent", {"intent": intent})

            # ── 5. Run handler ────────────────────────────────────────────────
            async for chunk in _run_handler(
                intent, question, history, session_id, reason=reason
            ):
                if isinstance(chunk, str):
                    full_answer += chunk
                    yield _sse("token", {"text": chunk})
                elif isinstance(chunk, dict) and "sources" in chunk:
                    sources = chunk["sources"]

            yield _sse("done", {
                "session_id": session_id,
                "intent":     intent,
                "sources":    sources,
            })

            add_to_history(session_id, "user",      question)
            add_to_history(session_id, "assistant", full_answer)

        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/sync")
async def chat_sync(request: Request):
    body       = await request.json()
    question   = body.get("question", "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)

    history     = get_history(session_id)
    full_answer = ""
    sources     = []

    active_intent = _get_active_flow(session_id)
    if active_intent:
        intent = active_intent
    else:
        escalate, reason = await should_escalate(question, history)
        if not escalate:
            intent = await classify_intent(question, history)
            if intent == "qa":
                rag_scores = _get_rag_scores(question)
                escalate, reason = await should_escalate(
                    question, history, rag_scores=rag_scores
                )
                if escalate:
                    intent = "escalate"
        else:
            intent = "escalate"
            reason = reason

    async for chunk in _run_handler(intent, question, history, session_id, reason=reason):
        if isinstance(chunk, str):
            full_answer += chunk
        elif isinstance(chunk, dict) and "sources" in chunk:
            sources = chunk["sources"]

    add_to_history(session_id, "user",      question)
    add_to_history(session_id, "assistant", full_answer)

    return {
        "session_id": session_id,
        "intent":     intent,
        "answer":     full_answer,
        "sources":    sources,
    }


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    clear_history(session_id)
    return {"cleared": session_id}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _run_handler(
    intent: str,
    question: str,
    history: list[dict],
    session_id: str,
    reason: str = "",
):
    """Dispatch to the correct handler generator."""
    if intent == "qa":
        async for c in handle_qa(question, history, session_id): yield c
    elif intent == "schedule":
        async for c in handle_schedule(question, history, session_id): yield c
    elif intent == "ticket":
        async for c in handle_ticket(question, history, session_id): yield c
    elif intent == "escalate":
        async for c in handle_escalate(question, history, session_id, reason=reason): yield c
    else:
        async for c in handle_qa(question, history, session_id): yield c


def _get_active_flow(session_id: str) -> str | None:
    """
    If the user is mid-way through a multi-turn flow, return that intent
    so we skip detection and continue the conversation.
    """
    for intent in ("schedule", "ticket", "escalate"):
        state = get_handler_state(session_id, intent)
        if state.get("step") and state["step"] != "start":
            return intent
    return None


def _get_rag_scores(question: str) -> list[float]:
    """
    Embed the question and retrieve top-k RAG scores.
    Used to decide if confidence is too low → escalate.
    """
    try:
        vec    = embed_query(question)
        chunks = search(vec, top_k=TOP_K)
        return [c["score"] for c in chunks]
    except Exception:
        return []


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
