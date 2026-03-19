"""
embedder.py
-----------
Converts a list of text strings into embedding vectors using
OpenAI text-embedding-3-small.

Key rule: ALWAYS use this same model + function at both:
  1. Ingestion time (embedding chunks to store)
  2. Query time     (embedding the user's question)

Batching: OpenAI allows up to 2048 texts per request.
We batch in groups of 100 to stay safely under limits and
allow progress reporting on large corpora.
"""

from openai import OpenAI
from config import OPENAI_API_KEY, EMBEDDING_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)

BATCH_SIZE = 100  # texts per API call


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings. Returns a list of float vectors,
    in the same order as the input.
    """
    if not texts:
        return []

    all_embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]

        response = _client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )

        # response.data is sorted by index — matches input order
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        print(f"[embedder] Embedded {min(i + BATCH_SIZE, len(texts))}/{len(texts)} texts")

    return all_embeddings


def embed_query(query: str) -> list[float]:
    """
    Embed a single user query at runtime.
    Must use the same model as embed_texts().
    """
    response = _client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[query],
    )
    return response.data[0].embedding


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = ["What is your pricing?", "How do I contact support?"]
    vecs = embed_texts(sample)
    print(f"Embedded {len(vecs)} texts. Vector dim: {len(vecs[0])}")
