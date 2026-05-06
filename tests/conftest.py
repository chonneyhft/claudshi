"""Shared fixtures for the test suite.

Two foundational fixtures unlock most of the suite:
  - `db` — a Database backed by a tmp-path SQLite file (file-based so the
    PRAGMA WAL journal mode set in Database.__init__ is valid).
  - `fake_kalshi` — a stub KalshiDataClient with overridable canned responses.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from engine.db import Database
from engine.paper_trader import PaperTrader


class FakeKalshi:
    """In-memory stand-in for KalshiDataClient.

    Tests configure responses by mutating `.markets` (ticker -> simplified market
    dict) and optionally `.events` / `.market_lists`. A market dict mirrors the
    output of `KalshiDataClient._simplify_market` (cents-denominated prices).
    """

    def __init__(self) -> None:
        self.markets: Dict[str, dict] = {}
        self.events: List[dict] = []
        self.market_lists: Dict[Optional[str], List[dict]] = {}
        self.calls: List[tuple] = []
        self.fail_tickers: set = set()

    def add_market(
        self,
        ticker: str,
        *,
        title: str = "Test Market",
        status: str = "open",
        yes_bid: Optional[int] = 50,
        yes_ask: Optional[int] = 52,
        no_bid: Optional[int] = 48,
        no_ask: Optional[int] = 50,
        last_price: Optional[int] = 51,
        result: Optional[str] = None,
        volume: int = 1000,
        open_interest: int = 500,
        close_time: str = "2099-12-31T00:00:00Z",
        category: str = "Test",
        event_ticker: str = "TESTEVT",
    ) -> dict:
        m = {
            "ticker": ticker,
            "event_ticker": event_ticker,
            "title": title,
            "category": category,
            "status": status,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no_bid": no_bid,
            "no_ask": no_ask,
            "last_price": last_price,
            "volume": volume,
            "open_interest": open_interest,
            "close_time": close_time,
            "result": result,
            "subtitle": "",
        }
        self.markets[ticker] = m
        return m

    def get_market(self, ticker: str) -> dict:
        self.calls.append(("get_market", ticker))
        if ticker in self.fail_tickers:
            raise RuntimeError(f"forced failure for {ticker}")
        if ticker not in self.markets:
            raise KeyError(f"unknown ticker {ticker}")
        return self.markets[ticker]

    def get_markets(
        self,
        limit: int = 20,
        category: Optional[str] = None,
        series_ticker: Optional[str] = None,
    ) -> list:
        self.calls.append(("get_markets", limit, category, series_ticker))
        return list(self.market_lists.get(series_ticker, []))[:limit]

    def get_events(self, limit: int = 20, **kwargs) -> list:
        self.calls.append(("get_events", limit, kwargs))
        return list(self.events)[:limit]

    def get_orderbook(self, ticker: str) -> dict:
        return {"yes": [], "no": []}

    def get_market_history(self, ticker: str, limit: int = 50) -> list:
        return []


@pytest.fixture
def fake_kalshi() -> FakeKalshi:
    return FakeKalshi()


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def trader(db, fake_kalshi) -> PaperTrader:
    return PaperTrader(db, fake_kalshi)
