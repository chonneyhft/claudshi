"""Tier 4: prompts — performance review math and prompt assembly."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

import config
from agent.prompts import _build_performance_review, build_system_prompt
from engine.models import Thesis


def _settled_thesis(**overrides) -> Thesis:
    base = dict(
        id="x", ticker="KX1", side_predicted="yes", category="Politics",
        entry_thesis="x", probability_estimate=70, market_price_at_entry=50,
        edge_cents=20, status="settled", outcome="win", realized_pnl_cents=100,
        session_id="s",
    )
    base.update(overrides)
    return Thesis(**base)


# ---------------------------------------------------------------------------
# _build_performance_review
# ---------------------------------------------------------------------------


def test_performance_review_empty_when_no_resolved_theses(db):
    assert _build_performance_review(db) == ""


def test_performance_review_excludes_active_theses(db):
    db.save_thesis(_settled_thesis(id="a", status="active"))
    assert _build_performance_review(db) == ""


def test_performance_review_aggregates_by_category(db):
    db.save_thesis(_settled_thesis(id="a", category="Politics", outcome="win",
                                   realized_pnl_cents=100, edge_cents=20))
    db.save_thesis(_settled_thesis(id="b", category="Politics", outcome="loss",
                                   realized_pnl_cents=-50, edge_cents=10))
    db.save_thesis(_settled_thesis(id="c", category="Tech", outcome="win",
                                   realized_pnl_cents=300, edge_cents=30))

    review = _build_performance_review(db)
    assert "Politics" in review
    assert "Tech" in review
    assert "Total theses resolved: 3" in review


def test_performance_review_calibration_band_requires_n_at_least_2(db):
    """Calibration section only renders bands with n >= 2."""
    # Single thesis at 70 -> no calibration
    db.save_thesis(_settled_thesis(id="a", probability_estimate=72, outcome="win"))
    review = _build_performance_review(db)
    assert "Calibration" not in review

    # Add a second 70-band thesis -> calibration renders
    db.save_thesis(_settled_thesis(id="b", probability_estimate=78, outcome="loss"))
    review = _build_performance_review(db)
    assert "Calibration" in review
    assert "70-79c estimates" in review


def test_performance_review_includes_closed_theses(db):
    db.save_thesis(_settled_thesis(id="a", status="closed", outcome="win"))
    review = _build_performance_review(db)
    assert "Total theses resolved: 1" in review


def test_performance_review_handles_uncategorized(db):
    db.save_thesis(_settled_thesis(id="a", category="", outcome="win"))
    review = _build_performance_review(db)
    assert "Uncategorized" in review


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_returns_two_part_structured(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_WEB_RESEARCH", True)
    parts = build_system_prompt(balance_cents=10000, num_positions=2, realized_pnl_cents=500)
    assert len(parts) == 2
    static, dynamic = parts
    assert static.get("cache_control") == {"type": "ephemeral"}
    assert "cache_control" not in dynamic
    assert "Research Mode" in dynamic["text"]
    assert "$100.00" in dynamic["text"]  # balance formatted


def test_build_system_prompt_no_research_mode(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_WEB_RESEARCH", False)
    parts = build_system_prompt(balance_cents=10000, num_positions=0, realized_pnl_cents=0)
    assert "No-Research Mode" in parts[1]["text"]
    assert "web_search" not in parts[0]["text"]


def test_build_system_prompt_includes_journal(monkeypatch, tmp_path):
    from agent import journal as journal_mod
    path = tmp_path / "journal.md"
    path.write_text("watching FOMC")
    monkeypatch.setattr(journal_mod, "JOURNAL_PATH", path)
    parts = build_system_prompt(balance_cents=0, num_positions=0, realized_pnl_cents=0)
    assert "watching FOMC" in parts[1]["text"]


def test_build_system_prompt_includes_market_feed():
    parts = build_system_prompt(
        balance_cents=0, num_positions=0, realized_pnl_cents=0,
        market_feed="## Market Feed\n| header |",
    )
    assert "## Market Feed" in parts[1]["text"]


def test_build_system_prompt_includes_perf_review_when_db_provided(db):
    db.save_thesis(_settled_thesis(id="a", outcome="win"))
    parts = build_system_prompt(
        balance_cents=0, num_positions=0, realized_pnl_cents=0, db=db,
    )
    assert "Performance Review" in parts[1]["text"]
