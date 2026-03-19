"""
ingest.py
---------
Orchestrates the full ingestion pipeline:
  scrape → chunk → embed → store

Run this once to populate the vector DB.
Re-run whenever the website content changes (it handles updates gracefully).

Usage:
  python ingest.py                        # ingest from SEED_URLS list below
  python ingest.py --clear                # wipe DB and re-ingest from scratch
"""

import asyncio
import argparse
from scraper  import scrape_site
from chunker  import chunk_pages
from embedder import embed_texts
from db       import setup_db, save_chunks, clear_chunks, get_stats
from config   import TARGET_URL, MAX_PAGES

# ── Add all the pages you want to include ────────────────────────────────────
# The scraper will crawl each URL AND follow all internal links found on it.
# So adding /home will also pick up anything linked from the home page.
SEED_URLS = [
    TARGET_URL,               # root domain — picks up whatever is in the nav
    f"{TARGET_URL}/use-cases/finance",
    f"{TARGET_URL}/use-cases/customer-support",
    f"{TARGET_URL}/use-cases/edtech",
    f"{TARGET_URL}/use-cases/healthcare",
    f"{TARGET_URL}/use-cases/voice-agents",
    f"{TARGET_URL}/voice",
    f"{TARGET_URL}/research",
    f"{TARGET_URL}/pricing",
    f"{TARGET_URL}/blog",
    f"{TARGET_URL}/spaces",
    f"{TARGET_URL}/docs",
    f"{TARGET_URL}/about-us",
]
# ─────────────────────────────────────────────────────────────────────────────

EMBED_BATCH = 200


async def ingest(seed_urls: list[str] = None, max_pages: int = MAX_PAGES, clear: bool = False):
    seed_urls = seed_urls or SEED_URLS

    print("=" * 60)
    print("RAG ingestion pipeline")
    print(f"Seeding from {len(seed_urls)} URLs, max {max_pages} pages total")
    print("=" * 60)

    # 0. Ensure DB schema exists
    setup_db()

    if clear:
        print("\n[ingest] --clear flag set. Wiping existing chunks...")
        clear_chunks()

    # 1. Scrape all seed URLs, deduplicating pages across seeds
    print("\n── Step 1: Scraping ──")
    all_pages = []
    seen_urls = set()

    for i, seed in enumerate(seed_urls, 1):
        print(f"\n[ingest] Seed {i}/{len(seed_urls)}: {seed}")
        try:
            pages = await scrape_site(seed_url=seed, max_pages=max_pages)
            new_pages = [p for p in pages if p["url"] not in seen_urls]
            for p in new_pages:
                seen_urls.add(p["url"])
            all_pages.extend(new_pages)
            print(f"[ingest] +{len(new_pages)} new pages (total so far: {len(all_pages)})")
        except Exception as e:
            print(f"[ingest] ✗ Failed to scrape {seed}: {e}")
            continue

    if not all_pages:
        print("[ingest] No pages scraped. Aborting.")
        return

    print(f"\n[ingest] Total unique pages scraped: {len(all_pages)}")

    # 2. Chunk
    print("\n── Step 2: Chunking ──")
    chunks = chunk_pages(all_pages)
    if not chunks:
        print("[ingest] No chunks produced. Aborting.")
        return

    # 3. Embed + store in batches
    print("\n── Step 3: Embedding + storing ──")
    for i in range(0, len(chunks), EMBED_BATCH):
        batch_chunks = chunks[i : i + EMBED_BATCH]
        texts = [c["text"] for c in batch_chunks]

        print(f"\n[ingest] Batch {i // EMBED_BATCH + 1}: embedding {len(batch_chunks)} chunks...")
        embeddings = embed_texts(texts)

        print(f"[ingest] Saving batch to DB...")
        save_chunks(batch_chunks, embeddings)

    # 4. Report
    stats = get_stats()
    print("\n" + "=" * 60)
    print("Ingestion complete!")
    print(f"  Total chunks stored : {stats['total_chunks']}")
    print(f"  Distinct pages      : {stats['total_pages']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest company website into RAG pipeline.")
    parser.add_argument("--clear", action="store_true", help="Clear DB before ingesting")
    parser.add_argument("--pages", default=MAX_PAGES, type=int, help="Max pages per seed URL")
    args = parser.parse_args()

    asyncio.run(ingest(max_pages=args.pages, clear=args.clear))