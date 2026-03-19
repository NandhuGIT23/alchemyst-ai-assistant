"""
handlers.py
-----------
One async generator per intent. Each yields str tokens then optionally
a dict with metadata (sources, next_action, etc.).

- handle_qa       : LIVE — calls RAG pipeline
- handle_schedule : AGENTIC — LLM drives the booking via tool calls
- handle_ticket   : AGENTIC — LLM drives ticket creation via tool calls
- handle_escalate : routes user to human support
"""

import sys, os, random, string, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'rag_pipeline'))

import openai
from rag_pipeline.query import answer_stream as rag_stream
from rag_pipeline.config import OPENAI_API_KEY, OPENAI_MODEL

from email_service    import send_ticket_email, send_demo_email
from calendar_service import get_available_slots
from session          import get_handler_state, set_handler_state, clear_handler_state

_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ticket_id() -> str:
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"TKT-{suffix}"

def _words(text: str):
    """Yield text word by word for streaming."""
    for word in text.split(" "):
        yield word + " "


# ── QA handler (unchanged) ────────────────────────────────────────────────────

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


# ── Agentic runner ────────────────────────────────────────────────────────────

async def _run_agent(
    session_id: str,
    intent: str,
    system_prompt: str,
    tools: list[dict],
    tool_executor,        # fn(name: str, args: dict) -> (result: dict, is_terminal: bool)
    question: str,
):
    """
    Drives an agentic tool-calling loop. Yields text tokens as the LLM speaks,
    calls tools autonomously, and loops until the LLM produces a plain text
    response (no tool calls). Saves / clears session state automatically.
    """
    state = get_handler_state(session_id, intent) if session_id else {}
    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": question})

    terminal_called = False

    while True:
        stream = await _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            tools=tools,
            tool_choice="auto",
            stream=True,
        )

        text = ""
        tool_calls_acc: dict[int, dict] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta

            if delta.content:
                text += delta.content
                yield delta.content

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    i = tc.index
                    if i not in tool_calls_acc:
                        tool_calls_acc[i] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tool_calls_acc[i]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[i]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[i]["arguments"] += tc.function.arguments

        if tool_calls_acc:
            # Append assistant message that requested the tool calls
            messages.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls_acc.values()
                ],
            })

            # Execute each tool and feed results back
            for tc in tool_calls_acc.values():
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}

                result, is_terminal = tool_executor(tc["name"], args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })
                if is_terminal:
                    terminal_called = True

            # Loop — let the LLM respond to the tool results

        else:
            # LLM produced a plain text response; conversation turn is complete
            messages.append({"role": "assistant", "content": text})

            if terminal_called:
                if session_id:
                    clear_handler_state(session_id, intent)
                yield {"sources": [], "next_action": "done"}
            else:
                if session_id:
                    set_handler_state(session_id, intent, {"messages": messages})
                yield {"sources": []}
            return


# ── Schedule handler (agentic) ────────────────────────────────────────────────

_SCHEDULE_SYSTEM = """\
You are a friendly demo booking assistant for Alchemyst AI.

Your goal: book a product demo for the user by collecting:
  - Email address  (required — needed to send confirmation)
  - A time slot    (required — fetch options with get_available_slots first)
  - Name           (optional — if the user skips or refuses, use "there")

Rules:
- Be conversational and flexible. Do NOT follow a rigid script.
- If the user has already provided information in the conversation, do not ask again.
- If the user declines to share their name, acknowledge it and proceed without it.
- Always call get_available_slots before presenting times so the list is live.
- Once you have the email and a chosen slot, call send_demo_email immediately.
- After send_demo_email returns, confirm the booking warmly to the user.\
"""

_SCHEDULE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Fetch live available demo time slots from the calendar.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_demo_email",
            "description": (
                "Book the demo and send a confirmation email to the user. "
                "Call this once you have the user's email and chosen slot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":       {"type": "string", "description": "Customer name. Use 'there' if not provided."},
                    "email":      {"type": "string", "description": "Customer email address."},
                    "slot_label": {"type": "string", "description": "Human-readable slot label from get_available_slots."},
                },
                "required": ["name", "email", "slot_label"],
            },
        },
    },
]


def _schedule_executor(name: str, args: dict) -> tuple[dict, bool]:
    if name == "get_available_slots":
        slots = get_available_slots()
        return {"slots": slots}, False

    if name == "send_demo_email":
        ok = send_demo_email(
            name=args.get("name", "there"),
            email=args.get("email", ""),
            slot=args.get("slot_label", ""),
        )
        return {"success": ok}, True

    return {"error": f"Unknown tool: {name}"}, False


async def handle_schedule(question: str, history: list[dict], session_id: str = None):
    async for chunk in _run_agent(
        session_id, "schedule",
        _SCHEDULE_SYSTEM, _SCHEDULE_TOOLS,
        _schedule_executor, question,
    ):
        yield chunk


# ── Ticket handler (agentic) ──────────────────────────────────────────────────

_TICKET_SYSTEM = """\
You are a helpful support ticket assistant for Alchemyst AI.

Your goal: raise a support ticket for the user by collecting:
  - Email address       (required — for follow-up)
  - Issue description   (required — ask for detail if the message is vague)
  - Name                (optional — use "Customer" if not provided)

Rules:
- Be empathetic and flexible. Do NOT follow a rigid script.
- If the user has already described their issue, do not ask them to repeat it.
- If the user skips their name, proceed without it.
- Once you have the email and a clear description, call create_support_ticket immediately.
- After the tool returns, share the ticket ID and confirm the next steps.\
"""

_TICKET_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_support_ticket",
            "description": (
                "Log a support ticket and send confirmation emails. "
                "Call this once you have the user's email and issue description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string", "description": "Customer name. Use 'Customer' if not provided."},
                    "email":       {"type": "string", "description": "Customer email address."},
                    "description": {"type": "string", "description": "Detailed description of the issue."},
                },
                "required": ["name", "email", "description"],
            },
        },
    },
]


def _ticket_executor(name: str, args: dict) -> tuple[dict, bool]:
    if name == "create_support_ticket":
        ticket_id = _ticket_id()
        ok = send_ticket_email(
            ticket_id=ticket_id,
            name=args.get("name", "Customer"),
            email=args.get("email", ""),
            description=args.get("description", ""),
        )
        return {"success": ok, "ticket_id": ticket_id}, True

    return {"error": f"Unknown tool: {name}"}, False


async def handle_ticket(question: str, history: list[dict], session_id: str = None):
    async for chunk in _run_agent(
        session_id, "ticket",
        _TICKET_SYSTEM, _TICKET_TOOLS,
        _ticket_executor, question,
    ):
        yield chunk


# ── Escalate handler ──────────────────────────────────────────────────────────

async def handle_escalate(question: str, history: list[dict], session_id: str = None):
    msg = (
        "Of course — I'll connect you with a member of our support team right away. 🤝\n\n"
        "To make sure the right person reaches out to you, could you share your "
        "**name** and **email address**? We typically respond within a few hours."
    )
    for w in _words(msg): yield w
    yield {"next_action": "collect_escalation_contact", "sources": []}
