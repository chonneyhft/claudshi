import logging
import os
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WebResearcher:
    def __init__(self):
        self.brave_api_key = os.getenv("BRAVE_API_KEY", "")
        self._last_search_time = 0.0
        self._min_search_interval = 1.1
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        if not self.brave_api_key:
            logger.warning("BRAVE_API_KEY not set — using DuckDuckGo fallback (unreliable, rate-limited)")

    def _rate_limit(self):
        elapsed = time.time() - self._last_search_time
        if elapsed < self._min_search_interval:
            time.sleep(self._min_search_interval - elapsed)
        self._last_search_time = time.time()

    def search(self, query: str, max_results: int = 5) -> List[dict]:
        self._rate_limit()
        if self.brave_api_key:
            return self._brave_search(query, max_results, search_type="web")
        return self._fallback_search(query, max_results)

    def search_news(self, query: str, max_results: int = 5) -> List[dict]:
        self._rate_limit()
        if self.brave_api_key:
            return self._brave_search(query, max_results, search_type="news")
        return self._fallback_search(query + " news", max_results)

    def _brave_search(self, query: str, max_results: int, search_type: str = "web") -> List[dict]:
        url = "https://api.search.brave.com/res/v1/web/search"
        if search_type == "news":
            url = "https://api.search.brave.com/res/v1/news/search"

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.brave_api_key,
        }
        params = {"q": query, "count": min(max_results, 20)}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Brave search failed: query=%r error=%s", query, e)
            return [{"error": f"SEARCH FAILED for '{query}': {e}. Do not assume absence of news — search is broken."}]

        if search_type == "news":
            results = data.get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                    "source": r.get("meta_url", {}).get("hostname", ""),
                    "date": r.get("age", ""),
                }
                for r in results[:max_results]
            ]
        else:
            results = data.get("web", {}).get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                }
                for r in results[:max_results]
            ]

    def _fallback_search(self, query: str, max_results: int) -> List[dict]:
        try:
            from duckduckgo_search import DDGS
            ddgs = DDGS()
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                logger.warning("DuckDuckGo returned no results: query=%r", query)
                return [{"error": f"SEARCH RETURNED NO RESULTS for '{query}'. DuckDuckGo may be rate-limiting. Do not assume absence of news — search is degraded."}]
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("DuckDuckGo search failed: query=%r error=%s", query, e)
            return [{"error": f"SEARCH FAILED for '{query}': {e}. Do not trade based on assumptions about current news — search is unavailable."}]

    def read_webpage(self, url: str, max_chars: int = 5000) -> dict:
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            return {"error": f"Failed to fetch URL: {e}"}

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        article = soup.find("article")
        if article:
            text = article.get_text(separator="\n", strip=True)
        else:
            main = soup.find("main") or soup.find("body")
            text = main.get_text(separator="\n", strip=True) if main else ""

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        if len(clean_text) > max_chars:
            clean_text = clean_text[:max_chars] + "\n...[truncated]"

        return {
            "title": title,
            "url": url,
            "content": clean_text,
        }
