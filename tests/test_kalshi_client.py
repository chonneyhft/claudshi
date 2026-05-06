"""Tier 2: KalshiDataClient — input parsing and HTTP behavior.

Pure-static helpers (`_dollars_to_cents`, `_simplify_market`) are tested
directly. The HTTP retry/backoff path is tested by stubbing `session.get`.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from kalshi.client import KalshiDataClient


# ---------------------------------------------------------------------------
# _dollars_to_cents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("val,expected", [
    (None, None),
    (0, 0),
    (0.65, 65),
    ("0.65", 65),
    (0.005, 0),  # banker's rounding: round(0.5) == 0
    (0.994, 99),
    (0.999, 100),
    (1.0, 100),
    ("not a number", None),
    ([], None),
    (-0.50, -50),
])
def test_dollars_to_cents(val, expected):
    assert KalshiDataClient._dollars_to_cents(val) == expected


# ---------------------------------------------------------------------------
# _simplify_market
# ---------------------------------------------------------------------------


def test_simplify_market_full_payload():
    raw = {
        "ticker": "KX1",
        "event_ticker": "EVT",
        "title": "Will X happen?",
        "category": "Politics",
        "status": "open",
        "yes_bid_dollars": 0.50,
        "yes_ask_dollars": 0.52,
        "no_bid_dollars": 0.48,
        "no_ask_dollars": 0.50,
        "last_price_dollars": 0.51,
        "volume_fp": 1234.0,
        "open_interest_fp": 567.0,
        "close_time": "2099-01-01T00:00:00Z",
        "result": "yes",
        "yes_sub_title": "subtitle",
    }
    out = KalshiDataClient._simplify_market(raw)
    assert out["ticker"] == "KX1"
    assert out["yes_bid"] == 50
    assert out["yes_ask"] == 52
    assert out["no_bid"] == 48
    assert out["no_ask"] == 50
    assert out["last_price"] == 51
    assert out["volume"] == 1234.0
    assert out["open_interest"] == 567.0
    assert out["result"] == "yes"
    assert out["subtitle"] == "subtitle"


def test_simplify_market_missing_fields_does_not_raise():
    out = KalshiDataClient._simplify_market({})
    assert out["ticker"] is None
    assert out["yes_bid"] is None
    assert out["result"] is None  # falsy result coerced to None


def test_simplify_market_prefers_fp_volume():
    raw = {"volume_fp": 999.0, "volume": 1, "open_interest_fp": 7.0, "open_interest": 0}
    out = KalshiDataClient._simplify_market(raw)
    assert out["volume"] == 999.0
    assert out["open_interest"] == 7.0


def test_simplify_market_falls_back_to_subtitle_when_no_yes_sub_title():
    out = KalshiDataClient._simplify_market({"subtitle": "fallback"})
    assert out["subtitle"] == "fallback"


def test_simplify_market_empty_string_result_becomes_none():
    out = KalshiDataClient._simplify_market({"result": ""})
    assert out["result"] is None


# ---------------------------------------------------------------------------
# HTTP layer (mocked)
# ---------------------------------------------------------------------------


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"{status_code}")
    return resp


@pytest.fixture
def client(monkeypatch):
    c = KalshiDataClient(base_url="https://example.test/api")
    # Skip rate-limit sleeps in tests
    monkeypatch.setattr(c, "_min_interval", 0.0)
    return c


def test_get_returns_parsed_json_on_success(client):
    client.session = MagicMock()
    client.session.get.return_value = _mock_response(200, {"hello": "world"})
    assert client._get("/foo") == {"hello": "world"}


def test_get_retries_on_429_then_succeeds(client, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    client.session = MagicMock()
    client.session.get.side_effect = [
        _mock_response(429),
        _mock_response(429),
        _mock_response(200, {"ok": True}),
    ]
    result = client._get("/foo")
    assert result == {"ok": True}
    assert client.session.get.call_count == 3


def test_get_raises_after_max_retries(client, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    client.session = MagicMock()
    client.session.get.return_value = _mock_response(429)
    from requests import HTTPError
    with pytest.raises(HTTPError):
        client._get("/foo")


def test_get_raises_on_non_429_http_error(client):
    client.session = MagicMock()
    client.session.get.return_value = _mock_response(500)
    from requests import HTTPError
    with pytest.raises(HTTPError):
        client._get("/foo")


def test_get_market_unwraps_market_envelope(client):
    client.session = MagicMock()
    payload = {"market": {"ticker": "KX1", "yes_ask_dollars": 0.5}}
    client.session.get.return_value = _mock_response(200, payload)
    out = client.get_market("KX1")
    assert out["ticker"] == "KX1"
    assert out["yes_ask"] == 50


def test_get_markets_simplifies_each(client):
    client.session = MagicMock()
    payload = {"markets": [
        {"ticker": "A", "yes_ask_dollars": 0.10},
        {"ticker": "B", "yes_ask_dollars": 0.90},
    ]}
    client.session.get.return_value = _mock_response(200, payload)
    out = client.get_markets()
    assert [m["ticker"] for m in out] == ["A", "B"]
    assert out[0]["yes_ask"] == 10


def test_get_markets_caps_limit_to_200(client):
    client.session = MagicMock()
    client.session.get.return_value = _mock_response(200, {"markets": []})
    client.get_markets(limit=500)
    _, kwargs = client.session.get.call_args
    assert kwargs["params"]["limit"] == 200


# ---------------------------------------------------------------------------
# search_series
# ---------------------------------------------------------------------------


def test_search_series_case_insensitive_match_across_fields(client):
    client.session = MagicMock()
    payload = {"series": [
        {"ticker": "KXCPI", "title": "CPI Inflation", "category": "Economics"},
        {"ticker": "KXGDP", "title": "GDP Growth", "category": "Economics"},
        {"ticker": "KXTRUMP", "title": "Election Outcome", "category": "Politics"},
    ]}
    client.session.get.return_value = _mock_response(200, payload)

    # Match by category (case-insensitive)
    out = client.search_series("ECONOMICS")
    assert {s["series_ticker"] for s in out} == {"KXCPI", "KXGDP"}


def test_search_series_match_by_ticker_substring(client):
    client.session = MagicMock()
    payload = {"series": [
        {"ticker": "KXCPI", "title": "x", "category": "y"},
        {"ticker": "KXFED", "title": "z", "category": "y"},
    ]}
    client.session.get.return_value = _mock_response(200, payload)
    out = client.search_series("cpi")
    assert len(out) == 1 and out[0]["series_ticker"] == "KXCPI"


def test_search_series_respects_limit(client):
    client.session = MagicMock()
    payload = {"series": [
        {"ticker": f"KX{i}", "title": "match me", "category": "cat"} for i in range(10)
    ]}
    client.session.get.return_value = _mock_response(200, payload)
    out = client.search_series("match", limit=3)
    assert len(out) == 3


def test_search_series_handles_missing_fields_gracefully(client):
    client.session = MagicMock()
    payload = {"series": [{"ticker": None, "title": None, "category": None}]}
    client.session.get.return_value = _mock_response(200, payload)
    out = client.search_series("anything")
    assert out == []


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------


def test_get_events_flattens_nested_markets(client):
    client.session = MagicMock()
    payload = {"events": [
        {
            "event_ticker": "EVT",
            "title": "Test Event",
            "category": "Tech",
            "markets": [
                {"ticker": "M1", "yes_ask_dollars": 0.30},
                {"ticker": "M2", "yes_ask_dollars": 0.70},
            ],
        }
    ]}
    client.session.get.return_value = _mock_response(200, payload)
    out = client.get_events()
    assert len(out) == 1
    assert out[0]["event_ticker"] == "EVT"
    assert [m["ticker"] for m in out[0]["markets"]] == ["M1", "M2"]
    assert out[0]["markets"][0]["yes_ask"] == 30
