"""
chunker.py
----------
Takes a list of scraped page dicts and returns a flat list of chunk dicts.

Each chunk carries:
  - text        : the chunk content (what goes to the embedder + LLM)
  - source_url  : the page it came from (shown as citation to user)
  - page_title  : human-readable page name
  - chunk_index : position within the page (0-based)

Strategy: RecursiveCharacterTextSplitter
  - Splits on paragraph → sentence → word boundaries (in that priority order)
  - ~500 tokens per chunk  (≈ 2000 characters at ~4 chars/token)
  - 50-token overlap       (≈ 200 characters) to avoid cutting answers in half
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import CHUNK_SIZE, CHUNK_OVERLAP


# 4 chars ≈ 1 token for English text — good enough for splitting purposes
CHARS_PER_TOKEN = 4

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE * CHARS_PER_TOKEN,          # ~2000 chars
    chunk_overlap=CHUNK_OVERLAP * CHARS_PER_TOKEN,    # ~200 chars
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],         # paragraph first
)


def chunk_pages(pages: list[dict]) -> list[dict]:
    """
    pages: output of scraper.scrape_site()
    Returns: flat list of chunk dicts ready for embedding.
    """
    all_chunks = []

    for page in pages:
        raw_text = page.get("text", "").strip()
        if not raw_text:
            continue

        splits = _splitter.split_text(raw_text)

        for idx, text in enumerate(splits):
            if len(text.strip()) < 40:   # skip tiny noise fragments
                continue
            all_chunks.append({
                "text":        text.strip(),
                "source_url":  page["url"],
                "page_title":  page.get("title", ""),
                "chunk_index": idx,
            })

    print(f"[chunker] {len(pages)} pages → {len(all_chunks)} chunks "
          f"(avg {len(all_chunks)//max(len(pages),1)} chunks/page)")
    return all_chunks


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_pages = [
        {
            "url":   "https://example.com/about",
            "title": "About Us",
            "text":  "We are a company.\n\n" * 40,   # simulate a real page
        }
    ]
    chunks = chunk_pages(sample_pages)
    print(f"Sample chunk:\n{chunks[0]}")
