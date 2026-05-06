"""Tier 3: ToolDispatcher — agent-facing tool surface.

Exercises every tool handler end-to-end against the real Database and a fake
Kalshi client. Confirms error-paths return JSON-encoded errors (the harness
relies on a `"error"` substring to count consecutive errors).
"""
from __future__ import annotations

import json

import pytest

import config
from agent.tools import ToolDispatcher, get_tools


SESSION = "test-session"


@pytest.fixture
def dispatcher(trader, fake_kalshi):
    return ToolDispatcher(fake_kalshi, trader, SESSION)


# ---------------------------------------------------------------------------
# get_tools
# ---------------------------------------------------------------------------


def test_get_tools_includes_research_when_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_WEB_RESEARCH", True)
    names = {t["name"] for t in get_tools()}
    assert {"web_search", "news_search", "read_webpage"}.issubset(names)


def test_get_tools_excludes_research_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_WEB_RESEARCH", False)
    names = {t["name"] for t in get_tools()}
    assert "web_search" not in names
    assert "place_trade" in names  # market tools still present


# ---------------------------------------------------------------------------
# dispatch error path
# ---------------------------------------------------------------------------


def test_dispatch_unknown_tool_returns_error_json(dispatcher):
    result = json.loads(dispatcher.dispatch("nonexistent", {}))
    assert "error" in result
    assert "Unknown tool" in result["error"]


def test_dispatch_handler_exception_is_serialized(dispatcher, fake_kalshi):
    # place_trade with a market that doesn't exist will raise
    result = json.loads(dispatcher.dispatch("place_trade", {
        "ticker": "MISSING", "side": "yes", "action": "buy",
        "quantity": 1, "reasoning": "x",
    }))
    assert "error" in result


# ---------------------------------------------------------------------------
# place_trade handler
# ---------------------------------------------------------------------------


def test_place_trade_handler_returns_filled_status(dispatcher, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=40)
    result = json.loads(dispatcher.dispatch("place_trade", {
        "ticker": "KX1", "side": "yes", "action": "buy",
        "quantity": 5, "reasoning": "thesis",
    }))
    assert result["status"] == "filled"
    assert result["ticker"] == "KX1"
    assert result["price_dollars"] == "$0.40"
    assert result["total_cost_dollars"] == "$2.00"


def test_place_trade_passes_thesis_id(dispatcher, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=40)
    # First create a thesis so a real ID exists
    th = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x", "probability_estimate": 60, "market_price_at_entry": 40,
    }))
    tid = th["thesis_id"]
    out = json.loads(dispatcher.dispatch("place_trade", {
        "ticker": "KX1", "side": "yes", "action": "buy",
        "quantity": 1, "reasoning": "x", "thesis_id": tid,
    }))
    assert out["thesis_id"] == tid


# ---------------------------------------------------------------------------
# Thesis handlers
# ---------------------------------------------------------------------------


def test_create_thesis_computes_edge(dispatcher):
    out = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "bullish", "probability_estimate": 75,
        "market_price_at_entry": 40,
    }))
    assert out["status"] == "created"
    assert out["edge_cents"] == 35
    assert "thesis_id" in out


def test_create_thesis_negative_edge(dispatcher):
    """Edge can be negative — recorded faithfully (the agent decided to enter anyway)."""
    out = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x", "probability_estimate": 30,
        "market_price_at_entry": 50,
    }))
    assert out["edge_cents"] == -20


def test_update_thesis_returns_error_for_missing_thesis(dispatcher):
    out = json.loads(dispatcher.dispatch("update_thesis", {
        "thesis_id": "doesnotexist", "probability_estimate": 80,
    }))
    assert "error" in out


def test_update_thesis_only_returns_changed_fields(dispatcher):
    th = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x", "probability_estimate": 60, "market_price_at_entry": 40,
    }))
    out = json.loads(dispatcher.dispatch("update_thesis", {
        "thesis_id": th["thesis_id"],
        "probability_estimate": 80,
        "category": "Politics",
    }))
    assert out["status"] == "updated"
    assert set(out["fields_updated"]) == {"probability_estimate", "category"}


def test_close_thesis_records_outcome(dispatcher):
    th = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x", "probability_estimate": 60, "market_price_at_entry": 40,
    }))
    out = json.loads(dispatcher.dispatch("close_thesis", {
        "thesis_id": th["thesis_id"],
        "exit_thesis": "took profit",
        "outcome": "win",
        "realized_pnl_cents": 200,
    }))
    assert out["status"] == "closed"
    assert out["outcome"] == "win"


def test_close_thesis_rejects_already_closed(dispatcher):
    th = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x", "probability_estimate": 60, "market_price_at_entry": 40,
    }))
    dispatcher.dispatch("close_thesis", {
        "thesis_id": th["thesis_id"], "exit_thesis": "x", "outcome": "win",
    })
    out = json.loads(dispatcher.dispatch("close_thesis", {
        "thesis_id": th["thesis_id"], "exit_thesis": "again", "outcome": "win",
    }))
    assert "error" in out
    assert "already closed" in out["error"]


def test_close_thesis_missing_returns_error(dispatcher):
    out = json.loads(dispatcher.dispatch("close_thesis", {
        "thesis_id": "nope", "exit_thesis": "x", "outcome": "win",
    }))
    assert "error" in out


def test_get_theses_returns_serializable_list(dispatcher):
    dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x" * 500, "probability_estimate": 60, "market_price_at_entry": 40,
    })
    out = json.loads(dispatcher.dispatch("get_theses", {"limit": 10}))
    assert len(out) == 1
    # entry_thesis truncated to 200 chars
    assert len(out[0]["entry_thesis"]) == 200


def test_get_theses_filters_by_status(dispatcher):
    th = json.loads(dispatcher.dispatch("create_thesis", {
        "ticker": "KX1", "side_predicted": "yes",
        "entry_thesis": "x", "probability_estimate": 60, "market_price_at_entry": 40,
    }))
    dispatcher.dispatch("close_thesis", {
        "thesis_id": th["thesis_id"], "exit_thesis": "x", "outcome": "win",
    })
    active = json.loads(dispatcher.dispatch("get_theses", {"status": "active"}))
    closed = json.loads(dispatcher.dispatch("get_theses", {"status": "closed"}))
    assert active == []
    assert len(closed) == 1


# ---------------------------------------------------------------------------
# Journal handler
# ---------------------------------------------------------------------------


def test_update_journal_writes_file(dispatcher, tmp_path, monkeypatch):
    journal_path = tmp_path / "journal.md"
    monkeypatch.setattr("agent.journal.JOURNAL_PATH", journal_path)
    out = json.loads(dispatcher.dispatch("update_journal", {"content": "hello"}))
    assert out["status"] == "saved"
    assert out["chars"] == 5
    assert journal_path.read_text() == "hello"
