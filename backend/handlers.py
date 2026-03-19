"""
handlers.py
-----------
One async generator per intent. Each yields str tokens then optionally
a dict with metadata (sources, next_action, etc.).

- handle_qa       : LIVE — calls RAG pipeline (Phase 1)
- handle_schedule : STUB — Phase 3 will replace this
- handle_ticket   : STUB — Phase 3 will replace this
- handle_escalate : STUB — Phase 4 will replace this
"""

import sys, os, random, string
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rag_pipeline'))

from rag_pipeline.query import answer_stream as rag_stream
from rag_pipeline.embedder import embed_query
from rag_pipeline.db import search


from email_service   import send_ticket_email, send_demo_email
from calendar_service import get_available_slots
from session         import get_handler_state, set_handler_state, clear_handler_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ticket_id() -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"TKT-{suffix}"

def _words(text: str):
    """Yield text word by word for streaming."""
    for word in text.split(" "):
        yield word + " "

def _is_valid_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1]


# ── QA handler (unchanged from Phase 2) ──────────────────────────────────────

async def handle_qa(question: str, history: list[dict], session_id: str = None):
    sources = []
    try:
        for chunk in rag_stream(question, history):
            if isinstance(chunk, str):
                yield chunk
            elif isinstance(chunk, dict) and "sources" in chunk:
                sources = chunk["sources"]
        yield {"sources": sources}
    except Exception:
        yield "Sorry, I ran into an issue retrieving that information. Please try again."
        yield {"sources": []}


# ── Schedule handler (multi-turn) ─────────────────────────────────────────────

async def handle_schedule(question: str, history: list[dict], session_id: str = None):
    """
    Turn-by-turn flow:
      start       → ask for name
      collect_name  → ask for email
      collect_email → fetch slots → show options
      collect_slot  → confirm → send emails → done
    """
    state = get_handler_state(session_id, "schedule") if session_id else {}
    step  = state.get("step", "start")
    data  = state.get("data", {})

    # ── start: greet and ask for name ────────────────────────────────────────
    if step == "start":
        set_handler_state(session_id, "schedule", {"step": "collect_name", "data": {}})
        msg = "I'd love to help you book a demo! 📅\n\nFirst, could you share your **full name**?"
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_name"}
        return

    # ── collect name → ask for email ─────────────────────────────────────────
    if step == "collect_name":
        name = question.strip().title()
        data["name"] = name
        set_handler_state(session_id, "schedule", {"step": "collect_email", "data": data})
        msg = f"Nice to meet you, **{name}**! What's the best email address to send your confirmation to?"
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_email"}
        return

    # ── collect email → fetch slots ───────────────────────────────────────────
    if step == "collect_email":
        email = question.strip().lower()
        if not _is_valid_email(email):
            msg = "That doesn't look like a valid email. Could you double-check and try again?"
            for w in _words(msg): yield w
            yield {"sources": []}
            return

        data["email"] = email
        # Fetch real slots from Google Calendar
        slots = get_available_slots()

        if not slots:
            set_handler_state(session_id, "schedule", {"step": "start", "data": {}})
            msg = (
                "I wasn't able to find any open slots right now. "
                "Please email us directly at sales@yourcompany.com and we'll sort something out!"
            )
            for w in _words(msg): yield w
            yield {"sources": []}
            return

        data["slots"] = slots
        set_handler_state(session_id, "schedule", {"step": "collect_slot", "data": data})

        slot_lines = "\n".join(
            f"  **{i+1}.** {s['label']}" for i, s in enumerate(slots)
        )
        msg = (
            f"Here are the next available slots:\n\n"
            f"{slot_lines}\n\n"
            f"Reply with **1**, **2**, or **3** to pick your preferred time."
        )
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_slot"}
        return

    # ── collect slot choice → confirm + send emails ───────────────────────────
    if step == "collect_slot":
        choice = question.strip()
        slots  = data.get("slots", [])
        name   = data.get("name", "there")
        email  = data.get("email", "")

        # Accept "1", "2", "3" or just pick first if unclear
        idx = None
        if choice in ("1", "2", "3"):
            idx = int(choice) - 1
        else:
            # Try to match slot label
            for i, s in enumerate(slots):
                if any(w in choice.lower() for w in s["label"].lower().split()):
                    idx = i
                    break

        if idx is None or idx >= len(slots):
            slot_lines = "\n".join(f"  **{i+1}.** {s['label']}" for i, s in enumerate(slots))
            msg = f"Please reply with **1**, **2**, or **3**:\n\n{slot_lines}"
            for w in _words(msg): yield w
            yield {"sources": []}
            return

        chosen = slots[idx]
        ok     = send_demo_email(name, email, chosen["label"])
        clear_handler_state(session_id, "schedule")

        if ok:
            msg = (
                f"You're all set, **{name}**! 🎉\n\n"
                f"Your demo is booked for **{chosen['label']}**. "
                f"We've sent a confirmation to **{email}** — our team will follow up with a calendar invite shortly."
            )
        else:
            msg = (
                f"Your slot **{chosen['label']}** is noted, but I had trouble sending the confirmation email. "
                f"Our team will reach out to **{email}** to confirm."
            )

        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "done"}
        return

    # Fallback: restart
    clear_handler_state(session_id, "schedule")
    for w in _words("Let's start over. What's your **full name**?"): yield w
    yield {"sources": []}


# ── Ticket handler (multi-turn) ───────────────────────────────────────────────

async def handle_ticket(question: str, history: list[dict], session_id: str = None):
    """
    Turn-by-turn flow:
      start          → ask for name
      collect_name   → ask for email
      collect_email  → ask for issue description
      collect_issue  → generate ticket ID → send email → done
    """
    state = get_handler_state(session_id, "ticket") if session_id else {}
    step  = state.get("step", "start")
    data  = state.get("data", {})

    # ── start ─────────────────────────────────────────────────────────────────
    if step == "start":
        set_handler_state(session_id, "ticket", {"step": "collect_name", "data": {}})
        msg = (
            "I'm sorry to hear you're having trouble. I'll get this logged right away. 🎫\n\n"
            "Could you start by sharing your **full name**?"
        )
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_name"}
        return

    # ── collect name ──────────────────────────────────────────────────────────
    if step == "collect_name":
        name = question.strip().title()
        data["name"] = name
        set_handler_state(session_id, "ticket", {"step": "collect_email", "data": data})
        msg = f"Thanks, **{name}**. What's your **email address** so we can follow up with you?"
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_email"}
        return

    # ── collect email ─────────────────────────────────────────────────────────
    if step == "collect_email":
        email = question.strip().lower()
        if not _is_valid_email(email):
            msg = "That doesn't look like a valid email. Could you double-check and re-enter it?"
            for w in _words(msg): yield w
            yield {"sources": []}
            return

        data["email"] = email
        set_handler_state(session_id, "ticket", {"step": "collect_issue", "data": data})
        msg = (
            "Got it. Now, please describe the issue you're experiencing in as much detail as you can — "
            "including any error messages or steps to reproduce it."
        )
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_issue"}
        return

    # ── collect issue → send ticket ───────────────────────────────────────────
    if step == "collect_issue":
        description = question.strip()

        if len(description) < 10:
            msg = "Could you give a bit more detail about the issue? The more context, the faster our team can help."
            for w in _words(msg): yield w
            yield {"sources": []}
            return

        name      = data.get("name", "Customer")
        email     = data.get("email", "")
        ticket_id = _ticket_id()

        ok = send_ticket_email(ticket_id, name, email, description)
        clear_handler_state(session_id, "ticket")

        if ok:
            msg = (
                f"Your ticket has been raised! ✅\n\n"
                f"**Ticket ID:** `{ticket_id}`\n\n"
                f"We've sent a confirmation to **{email}** and our support team will get back to you within **24 hours**. "
                f"Please keep your ticket ID handy for reference."
            )
        else:
            msg = (
                f"Your issue has been noted (ref: `{ticket_id}`), but I had trouble sending the email notification. "
                f"Please also email us directly at support@yourcompany.com quoting this reference."
            )

        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "done"}
        return

    # Fallback
    clear_handler_state(session_id, "ticket")
    for w in _words("Let's start over. What's your **full name**?"): yield w
    yield {"sources": []}


# ── Escalate handler (stub — Phase 4 will enhance) ────────────────────────────

async def handle_escalate(question: str, history: list[dict], session_id: str = None):
    msg = (
        "Of course — I'll connect you with a member of our support team right away. 🤝\n\n"
        "To make sure the right person reaches out to you, could you share your "
        "**name** and **email address**? We typically respond within a few hours."
    )
    for w in _words(msg): yield w
    yield {"next_action": "collect_escalation_contact", "sources": []}
