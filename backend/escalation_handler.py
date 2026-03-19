"""
escalation_handler.py
---------------------
Multi-turn escalation flow:

  detected   → acknowledge reason-specifically → ask for name
  collect_name  → ask for email
  collect_email → send escalation email → sign off

The handler receives the escalation "reason" from the detector
so it can give a tailored opening response.
"""

import random
import string
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rag_pipeline'))
from session          import get_handler_state, set_handler_state, clear_handler_state
from escalation_email import send_escalation_email


def _esc_id() -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ESC-{suffix}"

def _is_valid_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1]

def _words(text: str):
    for word in text.split(" "):
        yield word + " "

# Opening message tailored to each trigger reason
REASON_OPENERS = {
    "explicit": (
        "Of course — I'll connect you with a real person right away. 🤝\n\n"
        "To make sure the right team member reaches out, could you share your **full name**?"
    ),
    "frustrated": (
        "I'm really sorry you've had this experience — that's not the level of service we aim for. "
        "Let me get someone from our team to reach out to you directly. 🙏\n\n"
        "Could you share your **full name** so I can pass this along?"
    ),
    "sensitive": (
        "This is something I'd like to make sure our team handles personally. "
        "I'll flag it right away for a human to follow up with you. 🔒\n\n"
        "Could you share your **full name** to get started?"
    ),
    "low_confidence": (
        "That's a great question and I want to make sure you get the most accurate answer. "
        "Let me connect you with someone from our team who can help properly. 💬\n\n"
        "Could you share your **full name**?"
    ),
}


async def handle_escalate(
    question: str,
    history: list[dict],
    session_id: str = None,
    reason: str = "explicit",
):
    """
    Multi-turn escalation handler.
    reason: one of explicit | frustrated | sensitive | low_confidence
    """
    state = get_handler_state(session_id, "escalate") if session_id else {}
    step  = state.get("step", "start")
    data  = state.get("data", {})

    # ── start: acknowledge + ask for name ────────────────────────────────────
    if step == "start":
        set_handler_state(session_id, "escalate", {
            "step": "collect_name",
            "data": {"reason": reason},
        })
        opener = REASON_OPENERS.get(reason, REASON_OPENERS["explicit"])
        for w in _words(opener): yield w
        yield {"sources": [], "next_action": "collect_name"}
        return

    # ── collect name → ask for email ─────────────────────────────────────────
    if step == "collect_name":
        name = question.strip().title()
        data["name"] = name
        set_handler_state(session_id, "escalate", {"step": "collect_email", "data": data})
        msg = f"Thanks, **{name}**. What's the best **email address** for our team to reach you?"
        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "collect_email"}
        return

    # ── collect email → send notification → sign off ──────────────────────────
    if step == "collect_email":
        email = question.strip().lower()
        if not _is_valid_email(email):
            msg = "That doesn't look like a valid email. Could you re-enter it?"
            for w in _words(msg): yield w
            yield {"sources": []}
            return

        name         = data.get("name", "there")
        reason       = data.get("reason", "explicit")
        escalation_id = _esc_id()

        ok = send_escalation_email(
            name=name,
            email=email,
            reason=reason,
            last_message=question,
            history=history,
            escalation_id=escalation_id,
        )

        clear_handler_state(session_id, "escalate")

        if ok:
            msg = (
                f"You're all set, **{name}**. ✅\n\n"
                f"Our support team has been notified and will reach out to **{email}** "
                f"shortly — typically within a few hours during business hours.\n\n"
                f"Your reference ID is `{escalation_id}`. "
                f"Feel free to quote this if you email us directly."
            )
        else:
            msg = (
                f"I've noted your details, **{name}**, but had trouble sending the notification. "
                f"Please email us directly at support@yourcompany.com and mention "
                f"reference `{escalation_id}` — our team will prioritise it."
            )

        for w in _words(msg): yield w
        yield {"sources": [], "next_action": "done"}
        return

    # Fallback: restart
    clear_handler_state(session_id, "escalate")
    opener = REASON_OPENERS.get(reason, REASON_OPENERS["explicit"])
    for w in _words(opener): yield w
    yield {"sources": []}
