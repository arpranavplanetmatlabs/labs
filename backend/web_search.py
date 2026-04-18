"""
web_search.py — Tavily web search integration.

Flow:
  1. search_tavily(query, api_key) → List[str]    (URLs from Tavily)
  2. crawler.crawl_urls(urls) → List[str]           (page text)
  3. format_web_context(pages) → str                (merged string for LLM)
"""

import logging
import requests
from typing import List

logger = logging.getLogger(__name__)


def search_tavily(query: str, api_key: str, num_results: int = 5) -> List[str]:
    """
    Search via Tavily API. Returns a list of result URLs.
    Returns empty list if API key is missing or request fails.
    """
    if not api_key:
        logger.warning("[WebSearch] No Tavily API key configured — skipping web search")
        return []

    try:
        url = "https://api.tavily.com/search"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "max_results": num_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        urls = [r.get("url", "") for r in data.get("results", []) if r.get("url")]
        urls = [u for u in urls if u][:num_results]
        
        logger.info(f"[WebSearch] Tavily returned {len(urls)} URLs for: {query[:60]}")
        return urls

    except requests.RequestException as e:
        logger.error(f"[WebSearch] Tavily API error: {e}")
        return []


def crawl_and_format(urls: List[str]) -> str:
    """
    Crawl up to 3 URLs and return merged LLM-ready context block.
    Returns empty string if all pages fail.
    """
    try:
        from web_crawler import crawl_urls
        pages = crawl_urls(urls, max_pages=3, char_limit=4000)
    except Exception as e:
        logger.error(f"[WebSearch] Crawl error: {e}")
        pages = []
    return format_web_context(pages)


def format_web_context(pages: List[str]) -> str:
    """Merge crawled page texts into a single LLM-ready context block."""
    if not pages:
        return ""
    sections = "\n\n---\n\n".join(p.strip() for p in pages if p.strip())
    return f"=== WEB SEARCH RESULTS ===\n\n{sections}\n\n=== END WEB RESULTS ==="