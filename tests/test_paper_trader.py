"""Tier 1: PaperTrader — financial correctness.

Covers buy/sell flow, balance accounting, position averaging, and settlement.
These are the highest-leverage tests in the suite: bugs here directly corrupt
the persisted portfolio.
"""
from __future__ import annotations

import pytest

import config
from engine.models import Position, Thesis


SESSION = "test-session"


# ---------------------------------------------------------------------------
# Buy path
# ---------------------------------------------------------------------------


def test_buy_yes_decrements_balance_and_creates_position(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=60, yes_bid=58)

    starting_balance = config.STARTING_BALANCE_CENTS
    trade = trader.place_trade("KX1", "yes", "buy", 10, "thesis", SESSION)

    assert trade.action == "buy"
    assert trade.side == "yes"
    assert trade.quantity == 10
    assert trade.price_cents == 60  # yes_ask
    assert trade.total_cost_cents == 600

    portfolio = trader.get_portfolio()
    assert portfolio.balance_cents == starting_balance - 600
    assert len(portfolio.positions) == 1
    pos = portfolio.positions[0]
    assert pos.ticker == "KX1"
    assert pos.side == "yes"
    assert pos.quantity == 10
    assert pos.avg_price_cents == 60


def test_buy_no_uses_no_ask_price(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=70, no_ask=35)
    trade = trader.place_trade("KX1", "no", "buy", 5, "r", SESSION)
    assert trade.price_cents == 35
    assert trade.side == "no"


def test_buy_rejects_when_market_not_open(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", status="closed")
    with pytest.raises(ValueError, match="not open"):
        trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)


def test_buy_accepts_active_status(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", status="active", yes_ask=10)
    trade = trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)
    assert trade.price_cents == 10


def test_buy_rejects_when_no_ask_available(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=None)
    with pytest.raises(ValueError, match="No ask"):
        trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)


def test_buy_rejects_when_ask_is_zero(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=0)
    with pytest.raises(ValueError, match="No ask"):
        trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)


def test_buy_rejects_insufficient_balance(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_ask=99)
    huge_quantity = config.STARTING_BALANCE_CENTS  # 1 cent each * balance => exactly balance, plus 1 unit busts
    with pytest.raises(ValueError, match="Insufficient balance"):
        trader.place_trade("KX1", "yes", "buy", huge_quantity, "r", SESSION)


def test_buy_atomic_rollback_does_not_decrement_balance(trader, fake_kalshi, monkeypatch):
    """If position upsert fails mid-transaction, balance must roll back."""
    fake_kalshi.add_market("KX1", yes_ask=60)
    starting = config.STARTING_BALANCE_CENTS

    # Force the position write to fail after the balance has been mutated.
    def boom(pos):
        raise RuntimeError("simulated db error")

    monkeypatch.setattr(trader.db, "upsert_position", boom)
    with pytest.raises(RuntimeError, match="simulated"):
        trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)

    balance, _ = trader.db.get_portfolio_state()
    assert balance == starting, "balance must roll back when transaction fails"
    assert trader.db.get_positions() == []
    assert trader.db.get_trade_count() == 0


# ---------------------------------------------------------------------------
# Position averaging
# ---------------------------------------------------------------------------


def test_buying_same_ticker_averages_price(trader, fake_kalshi):
    m = fake_kalshi.add_market("KX1", yes_ask=60)
    trader.place_trade("KX1", "yes", "buy", 10, "r", SESSION)  # 10 @ 60
    m["yes_ask"] = 80
    trader.place_trade("KX1", "yes", "buy", 10, "r", SESSION)  # 10 @ 80

    positions = trader.db.get_positions()
    assert len(positions) == 1
    pos = positions[0]
    assert pos.quantity == 20
    assert pos.avg_price_cents == 70  # (10*60 + 10*80) / 20


def test_averaging_uses_floor_division_for_uneven_splits(trader, fake_kalshi):
    """avg = (60*1 + 61*1) // 2 = 60 (truncates, not rounds). Pin behavior."""
    m = fake_kalshi.add_market("KX1", yes_ask=60)
    trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)
    m["yes_ask"] = 61
    trader.place_trade("KX1", "yes", "buy", 1, "r", SESSION)
    pos = trader.db.get_positions()[0]
    assert pos.avg_price_cents == 60


# ---------------------------------------------------------------------------
# Sell path
# ---------------------------------------------------------------------------


def _open_long(trader, fake_kalshi, ticker="KX1", qty=10, ask=40):
    fake_kalshi.add_market(ticker, yes_ask=ask, yes_bid=ask - 2, no_ask=100 - ask + 2, no_bid=100 - ask)
    trader.place_trade(ticker, "yes", "buy", qty, "open", SESSION)


def test_sell_rejects_with_no_position(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", yes_bid=60)
    with pytest.raises(ValueError, match="No position"):
        trader.place_trade("KX1", "yes", "sell", 1, "r", SESSION)


def test_sell_rejects_on_side_mismatch(trader, fake_kalshi):
    _open_long(trader, fake_kalshi)  # opens YES
    with pytest.raises(ValueError, match="cannot sell no"):
        trader.place_trade("KX1", "no", "sell", 1, "r", SESSION)


def test_sell_rejects_oversell(trader, fake_kalshi):
    _open_long(trader, fake_kalshi, qty=5)
    with pytest.raises(ValueError, match="Only 5"):
        trader.place_trade("KX1", "yes", "sell", 6, "r", SESSION)


def test_sell_rejects_when_no_bid(trader, fake_kalshi):
    _open_long(trader, fake_kalshi)
    fake_kalshi.markets["KX1"]["yes_bid"] = None
    with pytest.raises(ValueError, match="No bid"):
        trader.place_trade("KX1", "yes", "sell", 1, "r", SESSION)


def test_partial_sell_reduces_quantity_and_records_pnl(trader, fake_kalshi):
    _open_long(trader, fake_kalshi, qty=10, ask=40)  # bought 10 @ 40
    fake_kalshi.markets["KX1"]["yes_bid"] = 70
    trader.place_trade("KX1", "yes", "sell", 4, "r", SESSION)

    positions = trader.db.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 6
    assert positions[0].avg_price_cents == 40  # avg unchanged on partial sell

    _, realized = trader.db.get_portfolio_state()
    assert realized == (70 - 40) * 4  # 120


def test_full_sell_deletes_position_and_credits_balance(trader, fake_kalshi):
    starting = config.STARTING_BALANCE_CENTS
    _open_long(trader, fake_kalshi, qty=10, ask=40)  # spent 400
    fake_kalshi.markets["KX1"]["yes_bid"] = 70
    trader.place_trade("KX1", "yes", "sell", 10, "r", SESSION)

    assert trader.db.get_positions() == []
    balance, realized = trader.db.get_portfolio_state()
    # Net: -400 (buy) + 700 (sell) = +300; realized = (70-40)*10 = 300
    assert balance == starting - 400 + 700
    assert realized == 300


def test_oversell_via_underlying_helper_is_clamped(trader, fake_kalshi):
    """_update_position_sell deletes when qty >= existing.quantity (defensive)."""
    _open_long(trader, fake_kalshi, qty=5, ask=40)
    # Bypass place_trade validation: call helper directly with an over-quantity.
    trader._update_position_sell("KX1", quantity=99, sell_price_cents=50)
    assert trader.db.get_positions() == []


# ---------------------------------------------------------------------------
# Settlement
# ---------------------------------------------------------------------------


def test_settle_yes_winner_pays_100(trader, fake_kalshi):
    starting = config.STARTING_BALANCE_CENTS
    _open_long(trader, fake_kalshi, qty=10, ask=40)  # spent 400, position avg 40
    fake_kalshi.markets["KX1"]["result"] = "yes"

    settled = trader.settle_positions()
    assert len(settled) == 1
    assert settled[0].action == "settle"
    assert settled[0].price_cents == 100
    assert settled[0].quantity == 10

    balance, realized = trader.db.get_portfolio_state()
    # -400 buy, +1000 settle => net +600; realized = (100-40)*10 = 600
    assert balance == starting - 400 + 1000
    assert realized == 600
    assert trader.db.get_positions() == []


def test_settle_yes_loser_pays_zero(trader, fake_kalshi):
    starting = config.STARTING_BALANCE_CENTS
    _open_long(trader, fake_kalshi, qty=10, ask=40)
    fake_kalshi.markets["KX1"]["result"] = "no"

    settled = trader.settle_positions()
    assert len(settled) == 1
    assert settled[0].price_cents == 0

    balance, realized = trader.db.get_portfolio_state()
    assert balance == starting - 400  # paid 400, got 0
    assert realized == (0 - 40) * 10  # -400


def test_settle_no_winner_pays_100_for_no_side(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", no_ask=30, yes_ask=72)
    trader.place_trade("KX1", "no", "buy", 5, "r", SESSION)
    fake_kalshi.markets["KX1"]["result"] = "no"

    settled = trader.settle_positions()
    assert settled[0].price_cents == 100
    _, realized = trader.db.get_portfolio_state()
    assert realized == (100 - 30) * 5


def test_settle_skips_unresolved_market(trader, fake_kalshi):
    _open_long(trader, fake_kalshi)
    # result remains None
    settled = trader.settle_positions()
    assert settled == []
    assert len(trader.db.get_positions()) == 1


def test_settle_skips_market_when_kalshi_fails(trader, fake_kalshi):
    _open_long(trader, fake_kalshi)
    fake_kalshi.fail_tickers.add("KX1")
    settled = trader.settle_positions()
    assert settled == []
    assert len(trader.db.get_positions()) == 1


def test_settle_updates_linked_thesis(trader, fake_kalshi):
    _open_long(trader, fake_kalshi, qty=4, ask=40)

    thesis = Thesis(
        id="th1",
        ticker="KX1",
        side_predicted="yes",
        entry_thesis="bullish",
        probability_estimate=70,
        market_price_at_entry=40,
        edge_cents=30,
        session_id=SESSION,
    )
    trader.db.save_thesis(thesis)

    fake_kalshi.markets["KX1"]["result"] = "yes"
    trader.settle_positions()

    refreshed = trader.db.get_thesis("th1")
    assert refreshed.status == "settled"
    assert refreshed.outcome == "win"
    assert refreshed.realized_pnl_cents == (100 - 40) * 4  # 240
    assert refreshed.closed_at is not None


def test_settle_marks_thesis_loss_on_zero_settle(trader, fake_kalshi):
    _open_long(trader, fake_kalshi, qty=4, ask=40)
    trader.db.save_thesis(Thesis(
        id="th2", ticker="KX1", side_predicted="yes", entry_thesis="x",
        probability_estimate=70, market_price_at_entry=40, session_id=SESSION,
    ))
    fake_kalshi.markets["KX1"]["result"] = "no"
    trader.settle_positions()
    assert trader.db.get_thesis("th2").outcome == "loss"


# ---------------------------------------------------------------------------
# Portfolio / snapshots
# ---------------------------------------------------------------------------


def test_get_portfolio_falls_back_to_avg_price_when_market_lookup_fails(trader, fake_kalshi):
    _open_long(trader, fake_kalshi, qty=10, ask=40)
    fake_kalshi.fail_tickers.add("KX1")
    portfolio = trader.get_portfolio()
    assert portfolio.positions[0].current_price_cents == 40


def test_get_portfolio_uses_no_bid_for_no_side(trader, fake_kalshi):
    fake_kalshi.add_market("KX1", no_ask=30, no_bid=33, yes_ask=72)
    trader.place_trade("KX1", "no", "buy", 5, "r", SESSION)
    portfolio = trader.get_portfolio()
    assert portfolio.positions[0].current_price_cents == 33


def test_take_snapshot_persists_row(trader, fake_kalshi):
    _open_long(trader, fake_kalshi)
    snapshots = trader.db.get_snapshots()
    # place_trade calls take_snapshot internally
    assert len(snapshots) >= 1
    assert snapshots[-1].num_positions == 1


def test_seed_portfolio_does_not_overwrite_balance(db, fake_kalshi):
    """Constructing a second PaperTrader against the same DB must not reset balance."""
    from engine.paper_trader import PaperTrader

    trader1 = PaperTrader(db, fake_kalshi)
    fake_kalshi.add_market("KX1", yes_ask=10)
    trader1.place_trade("KX1", "yes", "buy", 5, "r", SESSION)
    pre_balance, _ = db.get_portfolio_state()

    PaperTrader(db, fake_kalshi)  # re-seed attempt
    post_balance, _ = db.get_portfolio_state()
    assert post_balance == pre_balance
