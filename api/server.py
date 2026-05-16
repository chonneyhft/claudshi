"""Read-only JSON API over the same SQLite + JSONL sources the Streamlit
dashboard reads. Backs the Vite/React frontend in web/."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from engine.db import Database

app = FastAPI(title="Claudshi API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)


_db: Optional[Database] = None


def db() -> Database:
    global _db
    if _db is None:
        _db = Database(config.DB_PATH)
    return _db


def _cents(c: int) -> dict:
    return {"cents": c, "dollars": c / 100}


@app.get("/api/health")
def health():
    return {"ok": True, "ts": datetime.now().isoformat()}


@app.get("/api/portfolio")
def portfolio():
    d = db()
    balance, realized_pnl = d.get_portfolio_state()
    positions = d.get_positions()
    snapshots = d.get_snapshots()
    trade_count = d.get_trade_count()

    cost_basis = sum(p.avg_price_cents * p.quantity for p in positions)
    if snapshots:
        latest = snapshots[-1]
        positions_value = latest.positions_value_cents
        total_value = latest.total_value_cents
    else:
        positions_value = cost_basis
        total_value = balance + positions_value

    starting = config.STARTING_BALANCE_CENTS
    total_pnl = total_value - starting
    pct_return = (total_pnl / starting) * 100 if starting else 0

    return {
        "starting_balance": _cents(starting),
        "balance": _cents(balance),
        "positions_value": _cents(positions_value),
        "total_value": _cents(total_value),
        "cost_basis": _cents(cost_basis),
        "realized_pnl": _cents(realized_pnl),
        "unrealized_pnl": _cents(total_value - balance - cost_basis),
        "total_pnl": _cents(total_pnl),
        "pct_return": pct_return,
        "num_positions": len(positions),
        "num_trades": trade_count,
        "model": config.CLAUDE_MODEL,
        "interval_hours": config.TRADING_INTERVAL_SECONDS // 3600,
        "research_enabled": config.ENABLE_WEB_RESEARCH,
    }


@app.get("/api/positions")
def positions():
    d = db()
    positions = d.get_positions()
    out = []
    for p in positions:
        cost = p.avg_price_cents * p.quantity
        theses = d.get_theses_for_ticker(p.ticker)
        active = theses[0] if theses else None
        out.append({
            "ticker": p.ticker,
            "side": p.side,
            "quantity": p.quantity,
            "avg_price_cents": p.avg_price_cents,
            "cost_basis_cents": cost,
            "max_payout_cents": p.quantity * 100,
            "max_profit_cents": p.quantity * 100 - cost,
            "opened_at": p.opened_at.isoformat(),
            "thesis": {
                "id": active.id,
                "probability_estimate": active.probability_estimate,
                "market_price_at_entry": active.market_price_at_entry,
                "entry_thesis": active.entry_thesis,
                "edge_cents": active.edge_cents,
                "category": active.category,
            } if active else None,
        })
    return out


@app.get("/api/trades")
def trades(limit: int = 500):
    d = db()
    trades = d.get_trades(limit=limit)
    return [
        {
            "id": t.id,
            "ticker": t.ticker,
            "market_title": t.market_title,
            "side": t.side,
            "action": t.action,
            "quantity": t.quantity,
            "price_cents": t.price_cents,
            "total_cost_cents": t.total_cost_cents,
            "reasoning": t.reasoning,
            "session_id": t.session_id,
            "thesis_id": t.thesis_id,
            "timestamp": t.timestamp.isoformat(),
        }
        for t in trades
    ]


@app.get("/api/snapshots")
def snapshots():
    d = db()
    snaps = d.get_snapshots()
    return [
        {
            "timestamp": s.timestamp.isoformat(),
            "balance_cents": s.balance_cents,
            "positions_value_cents": s.positions_value_cents,
            "total_value_cents": s.total_value_cents,
            "realized_pnl_cents": s.realized_pnl_cents,
            "unrealized_pnl_cents": s.unrealized_pnl_cents,
            "num_positions": s.num_positions,
        }
        for s in snaps
    ]


@app.get("/api/theses")
def theses(status: Optional[str] = None, limit: int = 200):
    d = db()
    theses = d.get_theses(status=status, limit=limit)
    return [
        {
            "id": t.id,
            "ticker": t.ticker,
            "side_predicted": t.side_predicted,
            "category": t.category,
            "entry_thesis": t.entry_thesis,
            "probability_estimate": t.probability_estimate,
            "market_price_at_entry": t.market_price_at_entry,
            "edge_cents": t.edge_cents,
            "status": t.status,
            "exit_thesis": t.exit_thesis,
            "outcome": t.outcome,
            "realized_pnl_cents": t.realized_pnl_cents,
            "created_at": t.created_at.isoformat(),
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "session_id": t.session_id,
        }
        for t in theses
    ]


def _load_sessions() -> list[list[dict]]:
    log_dir = Path(config.LOG_DIR)
    if not log_dir.exists():
        return []
    out = []
    for log_file in sorted(log_dir.glob("*.jsonl"), reverse=True):
        entries = []
        for line in log_file.read_text().strip().split("\n"):
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if entries:
            out.append(entries)
    return out


@app.get("/api/sessions")
def sessions():
    """Lightweight session index — id, timestamp, summary stats."""
    out = []
    for entries in _load_sessions():
        head = entries[0]
        session_id = head.get("session_id", "?")
        ts = head.get("timestamp", "")
        summary = next((e for e in entries if e.get("type") == "session_summary"), None)
        assistant_turns = [e for e in entries if e.get("role") == "assistant"]
        total_tools = sum(len(e.get("tool_calls", []) or []) for e in assistant_turns)
        token_entries = [e for e in entries if e.get("token_usage")]
        total_in = sum(e["token_usage"].get("input_tokens", 0) for e in token_entries)
        total_out = sum(e["token_usage"].get("output_tokens", 0) for e in token_entries)
        est_cost = (total_in * 15 + total_out * 75) / 1_000_000

        out.append({
            "session_id": session_id,
            "timestamp": ts,
            "turns": len(assistant_turns),
            "tool_calls": total_tools,
            "trades_made": summary.get("trades_made", 0) if summary else 0,
            "portfolio_value": summary.get("portfolio_value_dollars") if summary else None,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "est_cost_dollars": est_cost,
        })
    return out


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: str):
    for entries in _load_sessions():
        sid = entries[0].get("session_id", "")
        if sid == session_id or sid.startswith(session_id):
            return {"session_id": sid, "entries": entries}
    raise HTTPException(status_code=404, detail="session not found")


@app.get("/api/cost-summary")
def cost_summary():
    log_dir = Path(config.LOG_DIR)
    if not log_dir.exists():
        return {"sessions": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_read": 0, "cache_write": 0, "est_cost_dollars": 0}
    entries = []
    for f in sorted(log_dir.glob("*.jsonl")):
        for line in f.read_text().strip().split("\n"):
            if line:
                try:
                    e = json.loads(line)
                    if e.get("token_usage"):
                        entries.append(e)
                except json.JSONDecodeError:
                    continue
    total_in = sum(e["token_usage"].get("input_tokens", 0) for e in entries)
    total_out = sum(e["token_usage"].get("output_tokens", 0) for e in entries)
    cache_read = sum(e["token_usage"].get("cache_read_input_tokens", 0) for e in entries)
    cache_write = sum(e["token_usage"].get("cache_creation_input_tokens", 0) for e in entries)
    return {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "est_cost_dollars": (total_in * 15 + total_out * 75) / 1_000_000,
    }
