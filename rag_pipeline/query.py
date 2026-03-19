"""
query.py
--------
Runtime query engine using OpenAI instead of Anthropic Claude.
"""

from openai import OpenAI
from embedder import embed_query
from db import search
from config import OPENAI_API_KEY, OPENAI_MODEL, MAX_TOKENS, TOP_K

_client = OpenAI(api_key=OPENAI_API_KEY)

# ── Prompt templates ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful assistant for our company. Your job is to answer questions accurately using only the provided context excerpts from our website.

Guidelines:
- Answer concisely and directly.
- If the context doesn't contain enough information to answer, say: "I don't have enough information on that — you may want to contact our support team."
- Never invent facts or make up information that isn't in the context.
- When relevant, mention which page the information came from.
- Keep answers friendly and professional."""


def _build_prompt(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return f"No relevant context found.\n\nUser question: {question}"

    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        context_blocks.append(
            f"[{i}] Source: {chunk['page_title'] or chunk['source_url']}\n"
            f"URL: {chunk['source_url']}\n"
            f"{chunk['text']}"
        )

    context_str = "\n\n---\n\n".join(context_blocks)

    return (
        f"Context from company website:\n\n"
        f"{context_str}\n\n"
        f"---\n\n"
        f"User question: {question}"
    )


def _format_history(history: list[dict]) -> list[dict]:
    return [
        {"role": msg["role"], "content": msg["content"]}
        for msg in history
        if msg.get("role") in ("user", "assistant") and msg.get("content")
    ]


# ── Main answer function ──────────────────────────────────────────────────────

def answer(
    question: str,
    history: list[dict] | None = None,
    top_k: int = TOP_K,
    stream: bool = False,
) -> dict:
    history = history or []

    # 1. Embed the user's question
    query_vec = embed_query(question)

    # 2. Retrieve relevant chunks
    chunks = search(query_vec, top_k=top_k)

    if not chunks:
        return {
            "answer": "I couldn't find relevant information to answer that question. Please contact our support team.",
            "sources": [],
            "chunks": [],
        }

    # 3. Build messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += _format_history(history)
    messages.append({
        "role": "user",
        "content": _build_prompt(question, chunks),
    })

    # 4. Call OpenAI
    if stream:
        stream_resp = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True,
        )
        return stream_resp

    response = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
    )

    answer_text = response.choices[0].message.content

    # 5. Deduplicate sources
    seen_urls = set()
    sources = []
    for chunk in chunks:
        if chunk["source_url"] not in seen_urls:
            sources.append({
                "url": chunk["source_url"],
                "title": chunk["page_title"] or chunk["source_url"],
                "score": chunk["score"],
            })
            seen_urls.add(chunk["source_url"])

    return {
        "answer": answer_text,
        "sources": sources,
        "chunks": chunks,
    }


# ── Streaming helper ──────────────────────────────────────────────────────────

def answer_stream(question: str, history: list[dict] | None = None):
    history = history or []

    query_vec = embed_query(question)
    chunks = search(query_vec)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += _format_history(history)
    messages.append({
        "role": "user",
        "content": _build_prompt(question, chunks),
    })

    stream = _client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        stream=True,
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

    # Sources at end
    seen = set()
    sources = []
    for chunk in chunks:
        if chunk["source_url"] not in seen:
            sources.append({
                "url": chunk["source_url"],
                "title": chunk["page_title"],
                "score": chunk["score"],
            })
            seen.add(chunk["source_url"])

    yield {"sources": sources}


# ── Interactive test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("RAG Query Engine — interactive test")
    print("Type 'quit' to exit.\n")

    history = []
    while True:
        q = input("You: ").strip()
        if q.lower() in ("quit", "exit", "q"):
            break
        if not q:
            continue

        result = answer(q, history=history)

        print(f"\nAssistant: {result['answer']}")

        if result["sources"]:
            print("\nSources:")
            for s in result["sources"]:
                print(f"  • {s['title']} — {s['url']} (score: {s['score']})")

        print()

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": result["answer"]})