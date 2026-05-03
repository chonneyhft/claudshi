import time
from typing import Dict, List, Optional

import requests

import config

MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


class KalshiDataClient:
    def __init__(self, base_url: str = config.KALSHI_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self._last_request_time = 0.0
        self._min_interval = 0.1

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

        url = f"{self.base_url}{path}"
        for attempt in range(MAX_RETRIES):
            self._last_request_time = time.time()
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * (attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()

        resp.raise_for_status()
        return {}

    def get_markets(
        self,
        limit: int = 20,
        category: Optional[str] = None,
        series_ticker: Optional[str] = None,
    ) -> List[dict]:
        params: dict = {"limit": min(limit, 200)}
        if category:
            params["category"] = category
        if series_ticker:
            params["series_ticker"] = series_ticker

        data = self._get("/markets", params)
        markets = data.get("markets", [])
        return [self._simplify_market(m) for m in markets]

    def get_market(self, ticker: str) -> dict:
        data = self._get(f"/markets/{ticker}")
        market = data.get("market", data)
        return self._simplify_market(market)

    def get_orderbook(self, ticker: str) -> dict:
        data = self._get(f"/markets/{ticker}/orderbook")
        return data.get("orderbook", data)

    def get_event(self, event_ticker: str) -> dict:
        data = self._get(f"/events/{event_ticker}")
        return data.get("event", data)

    def get_events(
        self,
        limit: int = 20,
        category: Optional[str] = None,
        series_ticker: Optional[str] = None,
        with_nested_markets: bool = True,
    ) -> List[dict]:
        params: dict = {"limit": min(limit, 50)}
        if category:
            params["category"] = category
        if series_ticker:
            params["series_ticker"] = series_ticker
        if with_nested_markets:
            params["with_nested_markets"] = "true"
        data = self._get("/events", params)
        events = data.get("events", [])
        result = []
        for e in events:
            event_info = {
                "event_ticker": e.get("event_ticker"),
                "title": e.get("title"),
                "category": e.get("category"),
            }
            markets = e.get("markets", [])
            event_info["markets"] = [self._simplify_market(m) for m in markets]
            result.append(event_info)
        return result

    def search_series(self, query: str, limit: int = 20) -> List[dict]:
        data = self._get("/series", {"limit": min(limit, 50)})
        all_series = data.get("series", [])
        query_lower = query.lower()
        matches = [
            {
                "series_ticker": s.get("ticker"),
                "title": s.get("title"),
                "category": s.get("category"),
            }
            for s in all_series
            if query_lower in (s.get("title", "") or "").lower()
            or query_lower in (s.get("ticker", "") or "").lower()
            or query_lower in (s.get("category", "") or "").lower()
        ]
        return matches[:limit]

    def get_market_history(self, ticker: str, limit: int = 50) -> List[dict]:
        params = {"ticker": ticker, "limit": limit}
        data = self._get("/trades", params)
        return data.get("trades", [])

    @staticmethod
    def _dollars_to_cents(val) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(round(float(val) * 100))
        except (ValueError, TypeError):
            return None

    @classmethod
    def _simplify_market(cls, m: dict) -> dict:
        return {
            "ticker": m.get("ticker"),
            "event_ticker": m.get("event_ticker"),
            "title": m.get("title"),
            "category": m.get("category"),
            "status": m.get("status"),
            "yes_bid": cls._dollars_to_cents(m.get("yes_bid_dollars")),
            "yes_ask": cls._dollars_to_cents(m.get("yes_ask_dollars")),
            "no_bid": cls._dollars_to_cents(m.get("no_bid_dollars")),
            "no_ask": cls._dollars_to_cents(m.get("no_ask_dollars")),
            "last_price": cls._dollars_to_cents(m.get("last_price_dollars")),
            "volume": m.get("volume_fp") or m.get("volume"),
            "open_interest": m.get("open_interest_fp") or m.get("open_interest"),
            "close_time": m.get("close_time"),
            "result": m.get("result") or None,
            "subtitle": m.get("yes_sub_title") or m.get("subtitle"),
        }
