"""Tier 1: Database — persistence and migration correctness.

Round-trips, transaction semantics, the migration path, and the
update-allowlist on `update_thesis`.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.db import Database
from engine.models import PerformanceSnapshot, Position, Thesis, Trade


def _trade(**overrides) -> Trade:
    base = dict(
        id="t1",
        ticker="KX1",
        market_title="Test",
        side="yes",
        action="buy",
        quantity=10,
        price_cents=50,
        total_cost_cents=500,
        reasoning="r",
        session_id="s1",
        thesis_id="",
    )
    base.update(overrides)
    return Trade(**base)


def _thesis(**overrides) -> Thesis:
    base = dict(
        id="th1",
        ticker="KX1",
        side_predicted="yes",
        category="Politics",
        entry_thesis="bullish",
        probability_estimate=70,
        market_price_at_entry=50,
        edge_cents=20,
        session_id="s1",
    )
    base.update(overrides)
    return Thesis(**base)


# ---------------------------------------------------------------------------
# Schema / seed / migration
# ---------------------------------------------------------------------------


def test_init_creates_all_tables(db):
    cur = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cur.fetchall()}
    expected = {"trades", "theses", "positions", "portfolio_state", "portfolio_snapshots"}
    assert expected.issubset(tables)


def test_seed_portfolio_only_inserts_once(db):
    db.seed_portfolio(10_000_00)
    db.seed_portfolio(99_000_00)  # second call should be a no-op
    balance, _ = db.get_portfolio_state()
    assert balance == 10_000_00


def test_get_portfolio_state_when_empty(tmp_path):
    db = Database(str(tmp_path / "empty.db"))
    # No seed_portfolio called
    assert db.get_portfolio_state() == (0, 0)


def test_migrate_adds_thesis_id_column_to_legacy_schema(tmp_path):
    """If a legacy DB exists without thesis_id, _migrate must add it."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE trades (
            id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            market_title TEXT,
            side TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price_cents INTEGER NOT NULL,
            total_cost_cents INTEGER NOT NULL,
            reasoning TEXT,
            session_id TEXT,
            timestamp TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

    db = Database(str(path))
    cur = db.conn.execute("PRAGMA table_info(trades)")
    cols = {row[1] for row in cur.fetchall()}
    assert "thesis_id" in cols


def test_migrate_is_idempotent(db):
    """Running _migrate twice must not error or duplicate columns."""
    db._migrate()
    db._migrate()
    cur = db.conn.execute("PRAGMA table_info(trades)")
    cols = [row[1] for row in cur.fetchall()]
    assert cols.count("thesis_id") == 1


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def test_transaction_commits_on_success(db):
    db.seed_portfolio(1000)
    with db.transaction():
        db.update_balance(2000)
    balance, _ = db.get_portfolio_state()
    assert balance == 2000


def test_transaction_rolls_back_on_exception(db):
    db.seed_portfolio(1000)
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.update_balance(9999)
            raise RuntimeError("boom")
    balance, _ = db.get_portfolio_state()
    assert balance == 1000


def test_balance_and_realized_pnl_independent(db):
    db.seed_portfolio(1000)
    db.add_realized_pnl(250)
    db.add_realized_pnl(-100)
    balance, realized = db.get_portfolio_state()
    assert balance == 1000
    assert realized == 150


# ---------------------------------------------------------------------------
# Trade round-trip
# ---------------------------------------------------------------------------


def test_save_and_get_trade_round_trip(db):
    t = _trade(reasoning="my reason", thesis_id="th1")
    db.save_trade(t)
    trades = db.get_trades()
    assert len(trades) == 1
    got = trades[0]
    assert got.id == "t1"
    assert got.reasoning == "my reason"
    assert got.thesis_id == "th1"
    assert got.timestamp.isoformat() == t.timestamp.isoformat()


def test_get_trades_orders_descending_by_timestamp(db):
    t1 = _trade(id="t1", timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc))
    t2 = _trade(id="t2", timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc))
    t3 = _trade(id="t3", timestamp=datetime(2024, 3, 1, tzinfo=timezone.utc))
    for t in (t1, t2, t3):
        db.save_trade(t)
    ids = [t.id for t in db.get_trades()]
    assert ids == ["t2", "t3", "t1"]


def test_get_trades_respects_limit(db):
    for i in range(5):
        db.save_trade(_trade(id=f"t{i}"))
    assert len(db.get_trades(limit=2)) == 2


def test_get_trade_count(db):
    assert db.get_trade_count() == 0
    db.save_trade(_trade())
    db.save_trade(_trade(id="t2"))
    assert db.get_trade_count() == 2


def test_trade_with_empty_thesis_id_round_trips_as_empty_string(db):
    db.save_trade(_trade(thesis_id=""))
    assert db.get_trades()[0].thesis_id == ""


# ---------------------------------------------------------------------------
# Thesis CRUD
# ---------------------------------------------------------------------------


def test_save_and_get_thesis_round_trip(db):
    t = _thesis()
    db.save_thesis(t)
    got = db.get_thesis("th1")
    assert got is not None
    assert got.id == "th1"
    assert got.probability_estimate == 70
    assert got.edge_cents == 20
    assert got.closed_at is None


def test_get_thesis_returns_none_when_missing(db):
    assert db.get_thesis("nonexistent") is None


def test_get_theses_filters_by_status_and_orders_desc(db):
    db.save_thesis(_thesis(id="a", status="active",
                           created_at=datetime(2024, 1, 1, tzinfo=timezone.utc)))
    db.save_thesis(_thesis(id="b", status="closed",
                           created_at=datetime(2024, 6, 1, tzinfo=timezone.utc)))
    db.save_thesis(_thesis(id="c", status="active",
                           created_at=datetime(2024, 3, 1, tzinfo=timezone.utc)))
    active = [t.id for t in db.get_theses(status="active")]
    assert active == ["c", "a"]
    all_theses = [t.id for t in db.get_theses()]
    assert all_theses == ["b", "c", "a"]


def test_get_theses_for_ticker_returns_only_active(db):
    db.save_thesis(_thesis(id="a", ticker="KX1", status="active"))
    db.save_thesis(_thesis(id="b", ticker="KX1", status="closed"))
    db.save_thesis(_thesis(id="c", ticker="KX2", status="active"))
    ids = sorted(t.id for t in db.get_theses_for_ticker("KX1"))
    assert ids == ["a"]


def test_update_thesis_allowlist_drops_disallowed_fields(db):
    db.save_thesis(_thesis(ticker="KX1"))
    # ticker is NOT in the allowlist; update_thesis must silently ignore it
    db.update_thesis("th1", ticker="HACKED", status="closed")
    got = db.get_thesis("th1")
    assert got.ticker == "KX1"
    assert got.status == "closed"


def test_update_thesis_drops_none_values(db):
    db.save_thesis(_thesis())
    db.update_thesis("th1", status=None, outcome="win")
    got = db.get_thesis("th1")
    assert got.status == "active"  # unchanged
    assert got.outcome == "win"


def test_update_thesis_with_no_valid_fields_is_noop(db):
    db.save_thesis(_thesis())
    db.update_thesis("th1", ticker="bogus")  # not allowed, gets filtered
    # Should not raise; and nothing should change
    assert db.get_thesis("th1").ticker == "KX1"


def test_update_thesis_persists_closed_at(db):
    db.save_thesis(_thesis())
    iso = datetime(2024, 5, 1, tzinfo=timezone.utc).isoformat()
    db.update_thesis("th1", closed_at=iso)
    assert db.get_thesis("th1").closed_at.isoformat() == iso


# ---------------------------------------------------------------------------
# Position CRUD
# ---------------------------------------------------------------------------


def test_upsert_position_inserts_then_updates(db):
    pos = Position(ticker="KX1", side="yes", quantity=10, avg_price_cents=50)
    db.upsert_position(pos)
    assert db.get_positions()[0].quantity == 10

    pos2 = Position(ticker="KX1", side="yes", quantity=20, avg_price_cents=55)
    db.upsert_position(pos2)
    positions = db.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 20
    assert positions[0].avg_price_cents == 55


def test_delete_position(db):
    db.upsert_position(Position(ticker="KX1", side="yes", quantity=1, avg_price_cents=50))
    db.delete_position("KX1")
    assert db.get_positions() == []


def test_delete_position_missing_is_noop(db):
    db.delete_position("nope")  # should not raise


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def test_save_and_read_snapshots_in_order(db):
    snaps = [
        PerformanceSnapshot(
            timestamp=datetime(2024, m, 1, tzinfo=timezone.utc),
            balance_cents=1000 + m,
            positions_value_cents=0,
            total_value_cents=1000 + m,
            realized_pnl_cents=0,
            unrealized_pnl_cents=0,
            num_positions=0,
        )
        for m in (3, 1, 2)
    ]
    for s in snaps:
        db.save_snapshot(s)
    rows = db.get_snapshots()
    assert [s.timestamp.month for s in rows] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Concurrency / re-open
# ---------------------------------------------------------------------------


def test_data_persists_across_database_instances(tmp_path):
    path = str(tmp_path / "persist.db")
    db1 = Database(path)
    db1.seed_portfolio(5000)
    db1.save_trade(_trade())
    db1.conn.close()

    db2 = Database(path)
    assert db2.get_trade_count() == 1
    balance, _ = db2.get_portfolio_state()
    assert balance == 5000
