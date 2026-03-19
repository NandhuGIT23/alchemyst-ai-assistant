"""
scraper.py
----------
Crawls a JS-rendered website using Crawl4AI.
Returns a list of { url, title, text } dicts — one per page.

Crawl4AI spins up a headless Chromium browser, waits for JS to settle,
then extracts clean markdown text (strips nav, footer, cookie banners).
"""

import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import NoExtractionStrategy
from config import TARGET_URL, MAX_PAGES


async def scrape_site(
    seed_url: str = TARGET_URL,
    max_pages: int = MAX_PAGES,
) -> list[dict]:
    """
    Crawl the site starting from seed_url.
    Returns a list of page dicts: { url, title, text }
    """
    browser_cfg = BrowserConfig(
        headless=True,
        verbose=False,
    )

    crawl_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,          # always fetch fresh content
        extraction_strategy=NoExtractionStrategy(),
        word_count_threshold=50,              # skip near-empty pages
        exclude_external_links=True,          # stay on same domain
        process_iframes=False,
        remove_overlay_elements=True,         # strip cookie/consent banners
        excluded_tags=["nav", "footer", "header", "script", "style"],
    )

    pages = []
    visited = set()

    # Collect all internal URLs from the seed page first
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        # Discover links from the seed page
        seed_result = await crawler.arun(url=seed_url, config=crawl_cfg)

        if not seed_result.success:
            print(f"[scraper] Failed to fetch seed URL: {seed_url}")
            return pages

        # Add seed page
        pages.append(_extract_page(seed_result))
        visited.add(seed_url)

        # Collect internal links
        links_to_visit = [
            link["href"]
            for link in (seed_result.links.get("internal") or [])
            if link.get("href") and link["href"] not in visited
        ]

        # Deduplicate and cap
        links_to_visit = list(dict.fromkeys(links_to_visit))[: max_pages - 1]

        print(f"[scraper] Seed page scraped. Found {len(links_to_visit)} internal links to crawl.")

        # Crawl remaining pages in batches of 5 (be polite to the server)
        batch_size = 5
        for i in range(0, len(links_to_visit), batch_size):
            batch = links_to_visit[i : i + batch_size]
            results = await crawler.arun_many(urls=batch, config=crawl_cfg)

            for result in results:
                if result.success and result.url not in visited:
                    page = _extract_page(result)
                    if page["text"].strip():  # skip blank pages
                        pages.append(page)
                        visited.add(result.url)
                        print(f"[scraper] ✓ {result.url}  ({len(page['text'])} chars)")
                else:
                    print(f"[scraper] ✗ {result.url}")

    print(f"\n[scraper] Done. Scraped {len(pages)} pages total.")
    return pages


def _extract_page(result) -> dict:
    """Pull url, title, and clean text from a CrawlResult."""
    return {
        "url":   result.url,
        "title": result.metadata.get("title", "") if result.metadata else "",
        "text":  result.markdown or result.cleaned_html or "",
    }


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pages = asyncio.run(scrape_site())
    for p in pages[:3]:
        print(f"\n--- {p['title']} ({p['url']}) ---")
        print(p["text"][:300])
