"""
escalation_detector.py
-----------------------
Escalates to a human agent ONLY when the user explicitly asks for one.
Uses the LLM to classify intent instead of keyword matching.

Usage in main.py:
  from escalation_detector import should_escalate
  if await should_escalate(question):
      intent = "escalate"
"""

import openai
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'rag_pipeline'))
from rag_pipeline.config import OPENAI_API_KEY, OPENAI_MODEL

_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)


# ── Main detector ──────────────────────────────────────────────────────────────

async def should_escalate(
    question: str,
    history: list[dict] = None,
    rag_scores: list[float] | None = None,
) -> tuple[bool, str]:
    """
    Returns (should_escalate: bool, reason: str).
    Uses the LLM to determine if the user is asking to speak to a human agent.
    """
    response = await _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a classifier. Determine if the user's message is asking "
                    "to speak with a human, live agent, or customer support representative. "
                    "Reply with only 'yes' or 'no'."
                ),
            },
            {"role": "user", "content": question},
        ],
        temperature=0,
        max_tokens=5,
    )

    answer = response.choices[0].message.content.strip().lower()
    if answer == "yes":
        return True, "explicit"

    return False, ""
