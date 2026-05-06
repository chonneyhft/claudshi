"""Tier 1: Pydantic models — derived properties.

Pure-logic tests for Position and Portfolio computed fields. These power
the dashboard, status output, and the agent's portfolio view.
"""
from __future__ import annotations

import pytest

from engine.models import Portfolio, Position, Thesis, Trade


def _pos(**overrides) -> Position:
    base = dict(
        ticker="KX1",
        side="yes",
        quantity=10,
        avg_price_cents=50,
        current_price_cents=60,
    )
    base.update(overrides)
    return Position(**base)


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


def test_position_cost_basis(_pos_helper=None):
    p = _pos(quantity=10, avg_price_cents=50)
    assert p.cost_basis_cents == 500


def test_position_market_value(_pos_helper=None):
    p = _pos(quantity=10, current_price_cents=60)
    assert p.market_value_cents == 600


def test_position_unrealized_pnl_positive():
    assert _pos(quantity=10, avg_price_cents=50, current_price_cents=60).unrealized_pnl_cents == 100


def test_position_unrealized_pnl_negative():
    assert _pos(quantity=10, avg_price_cents=70, current_price_cents=60).unrealized_pnl_cents == -100


def test_position_unrealized_pnl_zero_when_unpriced():
    """Default current_price_cents=0 makes unrealized = -cost_basis. Pin behavior."""
    p = _pos(current_price_cents=0)
    assert p.unrealized_pnl_cents == -p.cost_basis_cents


# ---------------------------------------------------------------------------
# Portfolio aggregates
# ---------------------------------------------------------------------------


def test_portfolio_with_no_positions():
    pf = Portfolio(balance_cents=1000)
    assert pf.positions_value_cents == 0
    assert pf.total_value_cents == 1000
    assert pf.unrealized_pnl_cents == 0
    assert pf.total_pnl_cents == 0


def test_portfolio_aggregates_across_positions():
    pf = Portfolio(
        balance_cents=1000,
        realized_pnl_cents=200,
        positions=[
            _pos(quantity=10, avg_price_cents=50, current_price_cents=60),  # +100
            _pos(quantity=5, avg_price_cents=80, current_price_cents=70),   # -50
        ],
    )
    assert pf.positions_value_cents == 600 + 350  # 950
    assert pf.total_value_cents == 1000 + 950
    assert pf.unrealized_pnl_cents == 100 - 50  # 50
    assert pf.total_pnl_cents == 200 + 50  # realized + unrealized


def test_portfolio_total_pnl_combines_realized_and_unrealized():
    pf = Portfolio(
        balance_cents=0,
        realized_pnl_cents=-300,
        positions=[_pos(quantity=10, avg_price_cents=50, current_price_cents=80)],
    )
    assert pf.unrealized_pnl_cents == 300
    assert pf.total_pnl_cents == 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_position_rejects_invalid_side():
    with pytest.raises(Exception):
        Position(ticker="KX1", side="maybe", quantity=1, avg_price_cents=50)


def test_trade_accepts_settle_action():
    """Regression: settle is a valid action (used by paper_trader._try_settle)."""
    Trade(
        id="t1", ticker="KX1", market_title="t", side="yes",
        action="settle", quantity=1, price_cents=100, total_cost_cents=100,
    )


def test_thesis_defaults():
    t = Thesis(
        id="th1", ticker="KX1", side_predicted="yes",
        entry_thesis="x", probability_estimate=70,
        market_price_at_entry=50, session_id="s",
    )
    assert t.status == "active"
    assert t.outcome == ""
    assert t.edge_cents == 0
    assert t.closed_at is None
