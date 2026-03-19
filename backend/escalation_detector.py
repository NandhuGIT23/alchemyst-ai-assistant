"""
escalation_detector.py
-----------------------
Checks all four escalation triggers BEFORE intent classification.
If any trigger fires, the message is routed to handle_escalate
regardless of what the intent classifier would say.

Four triggers (checked in order of priority):
  1. explicit    — user directly asks for a human / agent / person
  2. frustrated  — sentiment signals (caps, anger words, repeated complaints)
  3. sensitive   — legal, billing, refund, privacy, compliance topics
  4. low_confidence — RAG retrieval score below threshold (checked post-retrieval)

Usage in main.py:
  from escalation_detector import should_escalate
  if await should_escalate(question, history, rag_scores):
      intent = "escalate"
"""

import re
import openai
import openai
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rag_pipeline'))
from rag_pipeline.config import OPENAI_API_KEY, OPENAI_MODEL

_client = openai.OpenAI(api_key=OPENAI_API_KEY)

# ── Thresholds ────────────────────────────────────────────────────────────────
LOW_CONFIDENCE_THRESHOLD = 0.35   # cosine similarity below this → escalate

# ── Keyword lists ─────────────────────────────────────────────────────────────
EXPLICIT_PHRASES = [
    "talk to a human", "speak to a person", "speak to someone",
    "real person", "live agent", "human agent", "customer support",
    "talk to support", "connect me to", "transfer me", "escalate",
    "i want a person", "i need a person", "speak to a representative",
]

SENSITIVE_TOPICS = [
    "legal", "lawsuit", "sue", "attorney", "lawyer",
    "refund", "charge back", "chargeback", "billing issue", "overcharged",
    "fraud", "scam", "stolen", "unauthorized charge",
    "gdpr", "privacy", "data breach", "delete my data", "my data",
    "compliance", "regulation", "contract", "termination",
    "complaint", "unacceptable", "this is ridiculous",
]

FRUSTRATION_WORDS = [
    "frustrated", "angry", "furious", "useless", "terrible", "horrible",
    "worst", "pathetic", "incompetent", "disgusting", "ridiculous",
    "not working", "still broken", "keeps happening", "again and again",
    "no one helps", "nobody helps", "waste of time",
]


# ── Trigger 1: explicit human request ────────────────────────────────────────

def _is_explicit(text: str) -> bool:
    t = text.lower()
    return any(phrase in t for phrase in EXPLICIT_PHRASES)


# ── Trigger 2: frustrated sentiment ──────────────────────────────────────────

def _is_frustrated(text: str, history: list[dict]) -> bool:
    t = text.lower()

    # Keyword match
    if any(word in t for word in FRUSTRATION_WORDS):
        return True

    # Excessive caps (>40% uppercase in a message longer than 10 chars)
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 10 and sum(c.isupper() for c in letters) / len(letters) > 0.4:
        return True

    # Multiple exclamation or question marks
    if len(re.findall(r'[!?]', text)) >= 3:
        return True

    # Repeated complaints across history (user has complained before)
    complaint_count = sum(
        1 for m in history
        if m["role"] == "user" and any(w in m["content"].lower() for w in FRUSTRATION_WORDS)
    )
    if complaint_count >= 2:
        return True

    return False


# ── Trigger 3: sensitive topic ────────────────────────────────────────────────

def _is_sensitive(text: str) -> bool:
    t = text.lower()
    return any(topic in t for topic in SENSITIVE_TOPICS)


# ── Trigger 4: low RAG confidence ────────────────────────────────────────────

def _is_low_confidence(rag_scores: list[float]) -> bool:
    if not rag_scores:
        return True   # no chunks retrieved at all → escalate
    return max(rag_scores) < LOW_CONFIDENCE_THRESHOLD


# ── Main detector ─────────────────────────────────────────────────────────────

async def should_escalate(
    question: str,
    history: list[dict],
    rag_scores: list[float] | None = None,
) -> tuple[bool, str]:
    """
    Returns (should_escalate: bool, reason: str).
    reason is one of: "explicit" | "frustrated" | "sensitive" | "low_confidence"

    Call this BEFORE intent classification for the first three triggers.
    Call again AFTER RAG retrieval with rag_scores for the fourth trigger.
    """
    if _is_explicit(question):
        return True, "explicit"

    if _is_frustrated(question, history):
        return True, "frustrated"

    if _is_sensitive(question):
        return True, "sensitive"

    if rag_scores is not None and _is_low_confidence(rag_scores):
        return True, "low_confidence"

    return False, ""
