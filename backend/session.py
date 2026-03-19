"""
session.py  (Phase 3 — replaces Phase 2 version)
-------------------------------------------------
Extends the in-memory session store to also hold per-handler conversation state.

Structure per session_id:
  {
    "history": [ {role, content}, ... ],
    "handler_state": {
        "schedule": { "step": "...", "data": {...} },
        "ticket":   { "step": "...", "data": {...} },
        "escalate": { "step": "...", "data": {...} },
    },
    "last_active": timestamp
  }
"""

import time

MAX_TURNS   = 20
TTL_SECONDS = 60 * 60  # 1 hour

_store: dict[str, dict] = {}


# ── Conversation history ──────────────────────────────────────────────────────

def get_history(session_id: str) -> list[dict]:
    _prune_expired()
    session = _store.get(session_id)
    if not session:
        return []
    session["last_active"] = time.time()
    return session["history"]


def add_to_history(session_id: str, role: str, content: str):
    _ensure(session_id)
    _store[session_id]["history"].append({"role": role, "content": content})
    _store[session_id]["last_active"] = time.time()
    if len(_store[session_id]["history"]) > MAX_TURNS:
        _store[session_id]["history"] = _store[session_id]["history"][-MAX_TURNS:]


def clear_history(session_id: str):
    _store.pop(session_id, None)


# ── Handler state (multi-turn flows) ─────────────────────────────────────────

def get_handler_state(session_id: str, intent: str) -> dict:
    """Returns the current state dict for a given intent, or {} if not started."""
    _ensure(session_id)
    return _store[session_id]["handler_state"].get(intent, {})


def set_handler_state(session_id: str, intent: str, state: dict):
    """Persist the state dict for a given intent."""
    _ensure(session_id)
    _store[session_id]["handler_state"][intent] = state
    _store[session_id]["last_active"] = time.time()


def get_active_intent(session_id: str) -> str | None:
    """Return the intent name if a multi-turn flow is in progress, else None."""
    session = _store.get(session_id)
    if not session:
        return None
    for intent, state in session["handler_state"].items():
        if state.get("step"):
            return intent
    return None


def clear_handler_state(session_id: str, intent: str):
    """Clear state for an intent once the flow is complete."""
    if session_id in _store:
        _store[session_id]["handler_state"].pop(intent, None)


# ── Internal ──────────────────────────────────────────────────────────────────

def _ensure(session_id: str):
    if session_id not in _store:
        _store[session_id] = {
            "history":       [],
            "handler_state": {},
            "last_active":   time.time(),
        }


def _prune_expired():
    now     = time.time()
    expired = [sid for sid, s in _store.items()
               if now - s["last_active"] > TTL_SECONDS]
    for sid in expired:
        del _store[sid]
