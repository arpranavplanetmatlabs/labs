"""
web_crawler.py — Synchronous web page crawler for web search integration.

Fetches up to max_pages URLs, extracts clean text via BeautifulSoup,
truncates each page to char_limit chars. Returns list of text strings.

Dependencies: requests, beautifulsoup4
Install: pip install requests beautifulsoup4
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10        # seconds per request
_DEFAULT_CHAR_LIMIT = 4000   # chars per page
_DEFAULT_MAX_PAGES = 3

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Tags whose content we discard entirely
_SKIP_TAGS = {"script", "style", "nav", "footer", "header", "aside", "noscript", "form"}


def _extract_text(html: str) -> str:
    """Extract readable text from HTML, removing boilerplate tags."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("[WebCrawler] beautifulsoup4 not installed. Run: pip install beautifulsoup4")
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(_SKIP_TAGS):
        tag.decompose()

    raw = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _fetch_page(url: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Fetch a single URL. Returns HTML string or empty string on failure."""
    try:
        import requests
    except ImportError:
        logger.error("[WebCrawler] requests not installed. Run: pip install requests")
        return ""

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            logger.debug(f"[WebCrawler] Skipping non-HTML ({content_type}): {url}")
            return ""

        return resp.text

    except Exception as e:
        logger.warning(f"[WebCrawler] Failed to fetch {url}: {e}")
        return ""


def crawl_urls(
    urls: List[str],
    max_pages: int = _DEFAULT_MAX_PAGES,
    char_limit: int = _DEFAULT_CHAR_LIMIT,
) -> List[str]:
    """
    Crawl up to max_pages URLs. Returns list of text strings (one per page).
    Pages with no extractable text are excluded from the result.
    """
    results = []
    attempted = 0

    for url in urls:
        if attempted >= max_pages:
            break
        attempted += 1

        logger.info(f"[WebCrawler] Fetching ({attempted}/{max_pages}): {url}")
        html = _fetch_page(url)
        if not html:
            continue

        text = _extract_text(html)
        if not text:
            logger.debug(f"[WebCrawler] No text extracted from: {url}")
            continue

        truncated = text[:char_limit]
        if len(text) > char_limit:
            truncated += f"\n[truncated — full page at {url}]"

        results.append(f"Source: {url}\n\n{truncated}")
        logger.info(f"[WebCrawler] Extracted {len(truncated)} chars from: {url}")

    logger.info(f"[WebCrawler] Crawled {len(results)} pages from {attempted} URLs")
    return results
