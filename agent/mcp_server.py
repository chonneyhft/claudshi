"""Claudshi MCP server.

Exposes Kalshi market reads + paper trading + thesis/journal tools to any
MCP-aware host (Claude Code, Claude Desktop, etc.). Built-in host tools
(Bash, WebFetch, WebSearch) replace the agent's sandbox/research tools.

Run:
    python -m agent.mcp_server          # stdio transport
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

import config
from engine.db import Database
from engine.paper_trader import PaperTrader
from engine.models import Thesis
from kalshi.client import KalshiDataClient
from agent.journal import write_journal, read_journal

mcp = FastMCP("claudshi")

# Process-wide singletons. One MCP server == one trading account view.
db = Database(config.DB_PATH)
kalshi = KalshiDataClient()
trader = PaperTrader(db, kalshi)

# Sessions in the standalone harness are bounded runs. For MCP, each server
# process is effectively one session; generate an id at startup.
SESSION_ID = f"mcp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"


# --- Kalshi market reads ---------------------------------------------------

@mcp.tool()
def search_series(query: str) -> list[dict]:
    """Search Kalshi series by keyword."""
    return kalshi.search_series(query)


@mcp.tool()
def get_events(
    limit: int = 20,
    category: Optional[str] = None,
    series_ticker: Optional[str] = None,
) -> list[dict]:
    """Browse events with nested markets."""
    return kalshi.get_events(limit=limit, category=category, series_ticker=series_ticker)


@mcp.tool()
def get_market(ticker: str) -> dict:
    """Get single market detail."""
    return kalshi.get_market(ticker)


@mcp.tool()
def get_orderbook(ticker: str) -> dict:
    """Bid/ask depth for a market."""
    return kalshi.get_orderbook(ticker)


@mcp.tool()
def get_market_history(ticker: str, limit: int = 50) -> list[dict]:
    """Recent trades for a market."""
    return kalshi.get_market_history(ticker, limit=limit)


# --- Portfolio / trading ---------------------------------------------------

@mcp.tool()
def get_portfolio() -> dict:
    """Current balance, positions, realized + unrealized P&L."""
    p = trader.get_portfolio()
    return {
        "balance_cents": p.balance_cents,
        "realized_pnl_cents": p.realized_pnl_cents,
        "total_value_cents": p.total_value_cents,
        "total_pnl_cents": p.total_pnl_cents,
        "positions": [vars(pos) for pos in p.positions],
    }


@mcp.tool()
def get_trade_history(limit: int = 50) -> list[dict]:
    return [vars(t) for t in trader.get_trade_history(limit=limit)]


@mcp.tool()
def place_trade(
    ticker: str,
    side: str,         # "yes" | "no"
    action: str,       # "buy" | "sell"
    quantity: int,
    reasoning: str,
    thesis_id: Optional[str] = None,
) -> dict:
    """Place a paper trade. Link to a thesis_id from create_thesis when opening."""
    trade = trader.place_trade(
        ticker=ticker, side=side, action=action, quantity=quantity,
        reasoning=reasoning, session_id=SESSION_ID, thesis_id=thesis_id or "",
    )
    return {
        "status": "filled",
        "trade_id": trade.id,
        "ticker": trade.ticker,
        "price_dollars": f"${trade.price_cents / 100:.2f}",
        "total_cost_dollars": f"${trade.total_cost_cents / 100:.2f}",
        "thesis_id": trade.thesis_id or None,
    }


# --- Theses ----------------------------------------------------------------

@mcp.tool()
def create_thesis(
    ticker: str,
    side_predicted: str,
    entry_thesis: str,
    probability_estimate: int,    # 1-99
    market_price_at_entry: int,   # 1-99
    category: str = "",
) -> dict:
    """Open a structured thesis before placing a trade. Returns thesis_id."""
    tid = str(uuid.uuid4())[:12]
    thesis = Thesis(
        id=tid, ticker=ticker, side_predicted=side_predicted, category=category,
        entry_thesis=entry_thesis, probability_estimate=probability_estimate,
        market_price_at_entry=market_price_at_entry,
        edge_cents=probability_estimate - market_price_at_entry,
        status="active", created_at=datetime.now(timezone.utc),
        session_id=SESSION_ID,
    )
    trader.db.save_thesis(thesis)
    return {"thesis_id": tid, "edge_cents": thesis.edge_cents}


@mcp.tool()
def close_thesis(thesis_id: str, exit_thesis: str, outcome: str,
                 realized_pnl_cents: int = 0) -> dict:
    """Close a thesis on exit or settlement. outcome: win|loss|partial."""
    t = trader.db.get_thesis(thesis_id)
    if not t:
        return {"error": f"Thesis {thesis_id} not found"}
    trader.db.update_thesis(
        thesis_id, status="closed", exit_thesis=exit_thesis, outcome=outcome,
        realized_pnl_cents=realized_pnl_cents,
        closed_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"status": "closed", "thesis_id": thesis_id}


@mcp.tool()
def get_theses(status: Optional[str] = None, limit: int = 20) -> list[dict]:
    """status: active|closed|settled|None for all."""
    return [
        {
            "id": t.id, "ticker": t.ticker, "side_predicted": t.side_predicted,
            "probability_estimate": t.probability_estimate,
            "market_price_at_entry": t.market_price_at_entry,
            "edge_cents": t.edge_cents, "status": t.status, "outcome": t.outcome,
            "realized_pnl_cents": t.realized_pnl_cents,
        }
        for t in trader.db.get_theses(status=status, limit=limit)
    ]


# (update_thesis omitted from sketch — same pattern as close_thesis)


# --- Settlement ------------------------------------------------------------

@mcp.tool()
def reconcile_settlements() -> dict:
    """Settle any positions whose markets have resolved on Kalshi. Updates
    balances, realized P&L, and marks linked theses as settled. Returns a
    summary of what changed."""
    settled = trader.settle_positions()
    return {
        "settled_count": len(settled),
        "trades": [
            {
                "ticker": t.ticker,
                "side": t.side,
                "quantity": t.quantity,
                "settle_price_cents": t.price_cents,
                "reasoning": t.reasoning,
            }
            for t in settled
        ],
    }


# --- Resources -------------------------------------------------------------

@mcp.resource("portfolio://snapshot")
def portfolio_snapshot() -> str:
    """Current portfolio state — balance, positions, P&L, active theses.
    Pull at session start instead of round-tripping multiple tools."""
    p = trader.get_portfolio()
    active = trader.db.get_theses(status="active", limit=50)
    snapshot = {
        "session_id": SESSION_ID,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "balance_cents": p.balance_cents,
        "realized_pnl_cents": p.realized_pnl_cents,
        "total_value_cents": p.total_value_cents,
        "total_pnl_cents": p.total_pnl_cents,
        "positions": [vars(pos) for pos in p.positions],
        "active_theses": [
            {
                "id": t.id, "ticker": t.ticker, "side": t.side_predicted,
                "prob": t.probability_estimate, "entry_price": t.market_price_at_entry,
                "edge_cents": t.edge_cents,
            }
            for t in active
        ],
    }
    return json.dumps(snapshot, default=str, indent=2)


@mcp.resource("market://{ticker}/snapshot")
def market_snapshot(ticker: str) -> str:
    """Per-market snapshot: detail + orderbook + recent trades, in one read."""
    def _safe(fn, default):
        try:
            return fn()
        except Exception as e:
            return {"error": str(e), "value": default}
    return json.dumps({
        "market": kalshi.get_market(ticker),
        "orderbook": _safe(lambda: kalshi.get_orderbook(ticker), None),
        "recent_trades": _safe(lambda: kalshi.get_market_history(ticker, limit=20), []),
    }, default=str, indent=2)


# --- Journal ---------------------------------------------------------------

@mcp.tool()
def read_trading_journal() -> str:
    """Read the current journal."""
    return read_journal()


@mcp.tool()
def write_trading_journal(content: str) -> dict:
    """Overwrite the journal. Keep concise: Watchlist, Key Research, Strategy."""
    write_journal(content)
    return {"status": "saved", "chars": len(content)}


if __name__ == "__main__":
    mcp.run()  # stdio
