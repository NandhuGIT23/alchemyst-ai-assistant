"""
intent.py
---------
Classifies the user's message into one of four intents using OpenAI.

Intents:
  qa        — general company question → RAG pipeline
  schedule  — wants to book / schedule a demo call
  ticket    — reporting a problem / raising a support issue
  escalate  — wants human help, frustrated, sensitive topic

Uses a single fast OpenAI call with a structured prompt.
Returns the intent string.
"""

import json
import sys, os
from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rag_pipeline'))
from rag_pipeline.config import OPENAI_API_KEY, OPENAI_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)

INTENT_SYSTEM = """You are an intent classifier for a company chatbot. 
Classify the user's latest message into EXACTLY one of these intents:

- qa        : general question about the company, product, pricing, features, docs
- schedule  : wants to book, schedule, or arrange a demo, meeting, or call
- ticket    : reporting a bug, error, problem, or wants to raise a support issue
- escalate  : wants to talk to a human, is frustrated, or the topic is sensitive/complex

Reply with ONLY a JSON object: {"intent": "<one of the four>"}
No explanation. No markdown. Just the JSON."""


async def classify_intent(question: str, history: list[dict]) -> str:
    """
    Classify intent of the latest user message.
    Falls back to 'qa' on any error.
    """
    # Build a short context window — last 4 turns is enough for intent
    recent = history[-4:] if len(history) >= 4 else history
    messages = recent + [{"role": "user", "content": question}]

    try:
        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM},
                *messages
            ],
            max_tokens=20,
            temperature=0
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences the LLM sometimes adds
        if raw.startswith("```"):
            raw = raw.strip("`").removeprefix("json").strip()

        if not raw:
            print("[intent] Empty response from LLM, defaulting to qa")
            return "qa"

        data = json.loads(raw)
        print(f"[intent] Classified intent: {data}")
        intent = data.get("intent", "qa")

        if intent not in ("qa", "schedule", "ticket", "escalate"):
            return "qa"
        return intent

    except Exception as e:
        print(f"[intent] Classification failed ({e}), defaulting to qa")
        return "qa"