"""Tier 2: market_feed builder.

Verifies graceful degradation when Kalshi calls fail, dedup across sections,
and number formatting.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import config
from agent.market_feed import _fmt_num, _parse_num, build_market_feed


# ---------------------------------------------------------------------------
# Number helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("val,expected", [
    (None, 0.0),
    (0, 0.0),
    (123, 123.0),
    ("456", 456.0),
    ("abc", 0.0),
    ([], 0.0),
])
def test_parse_num(val, expected):
    assert _parse_num(val) == expected


@pytest.mark.parametrize("val,expected", [
    (0, "0"),
    (500, "500"),
    (999, "999"),
    (1_000, "1.0K"),
    (1_500, "1.5K"),
    (999_999, "1000.0K"),  # boundary just below 1M
    (1_000_000, "1.0M"),
    (2_500_000, "2.5M"),
])
def test_fmt_num(val, expected):
    assert _fmt_num(val) == expected


# ---------------------------------------------------------------------------
# build_market_feed
# ---------------------------------------------------------------------------


def _future_close() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


def test_build_feed_empty_when_nothing_to_show(fake_kalshi):
    out = build_market_feed(fake_kalshi, held_tickers=[])
    assert out == ""


def test_build_feed_includes_held_positions(fake_kalshi):
    fake_kalshi.add_market("KX1", title="Held market", volume=50, open_interest=10,
                           close_time=_future_close())
    out = build_market_feed(fake_kalshi, held_tickers=["KX1"])
    assert "Your Positions" in out
    assert "KX1" in out
    assert "Held market" in out


def test_build_feed_swallows_held_market_lookup_errors(fake_kalshi):
    """If get_market fails for a held ticker, feed must not crash."""
    fake_kalshi.fail_tickers.add("KX_BAD")
    # Should not raise
    out = build_market_feed(fake_kalshi, held_tickers=["KX_BAD"])
    assert "Your Positions" not in out  # no successful row


def test_build_feed_dedups_held_ticker_from_watchlist(fake_kalshi, monkeypatch):
    """A ticker held as a position must not also appear in Watchlist section."""
    monkeypatch.setattr(config, "WATCHED_SERIES", ["KXTEST"])
    held = fake_kalshi.add_market("KX1", close_time=_future_close())
    # Watchlist returns KX1 too
    fake_kalshi.market_lists["KXTEST"] = [held]

    out = build_market_feed(fake_kalshi, held_tickers=["KX1"])
    # KX1 should appear exactly once
    assert out.count("| KX1 |") == 1


def test_build_feed_watchlist_skips_non_open_markets(fake_kalshi, monkeypatch):
    monkeypatch.setattr(config, "WATCHED_SERIES", ["KXTEST"])
    closed = fake_kalshi.add_market("KX1", status="closed", close_time=_future_close())
    fake_kalshi.market_lists["KXTEST"] = [closed]
    out = build_market_feed(fake_kalshi, held_tickers=[])
    assert "KX1" not in out


def test_build_feed_continues_when_a_watchlist_series_fails(fake_kalshi, monkeypatch):
    """One failing series must not break the whole feed."""
    monkeypatch.setattr(config, "WATCHED_SERIES", ["KXFAIL", "KXOK"])

    ok = fake_kalshi.add_market("KX_OK", close_time=_future_close())
    original = fake_kalshi.get_markets

    def selective_get_markets(limit=20, category=None, series_ticker=None):
        if series_ticker == "KXFAIL":
            raise RuntimeError("series failed")
        if series_ticker == "KXOK":
            return [ok]
        return original(limit=limit, category=category, series_ticker=series_ticker)

    fake_kalshi.get_markets = selective_get_markets
    out = build_market_feed(fake_kalshi, held_tickers=[])
    assert "KX_OK" in out


def test_build_feed_trending_filters_by_volume_and_close_time(fake_kalshi):
    """Trending section requires volume > 500, status open/active, close within 1 year, no KXMVE."""
    fake_kalshi.events = [{
        "event_ticker": "EVT",
        "title": "ev",
        "category": "Tech",
        "markets": [
            # qualifies
            {"ticker": "GOOD", "title": "ok", "status": "open", "volume": 1000,
             "close_time": _future_close()},
            # fails: volume too low
            {"ticker": "LOW_VOL", "title": "x", "status": "open", "volume": 100,
             "close_time": _future_close()},
            # fails: closed
            {"ticker": "CLOSED", "title": "x", "status": "closed", "volume": 1000,
             "close_time": _future_close()},
            # fails: KXMVE prefix excluded
            {"ticker": "KXMVE_FOO", "title": "x", "status": "open", "volume": 1000,
             "close_time": _future_close()},
            # fails: closes too far in future (>1 year)
            {"ticker": "FAR", "title": "x", "status": "open", "volume": 1000,
             "close_time": (datetime.now(timezone.utc) + timedelta(days=400)).isoformat()},
        ],
    }]
    out = build_market_feed(fake_kalshi, held_tickers=[])
    assert "GOOD" in out
    assert "LOW_VOL" not in out
    assert "CLOSED" not in out
    assert "KXMVE_FOO" not in out
    assert "FAR" not in out


def test_build_feed_trending_swallows_event_fetch_failure(fake_kalshi, monkeypatch):
    def explode(*a, **kw):
        raise RuntimeError("api down")
    fake_kalshi.get_events = explode
    out = build_market_feed(fake_kalshi, held_tickers=[])
    # Should not raise; feed is just empty
    assert out == ""
