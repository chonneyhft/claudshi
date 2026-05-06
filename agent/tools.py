import json
from typing import List, Optional

import config
from engine.paper_trader import PaperTrader
from kalshi.client import KalshiDataClient

MARKET_TOOLS = [
    {
        "name": "run_python",
        "description": "Execute Python code to research markets, check your portfolio, and analyze data. "
        "The code runs in a subprocess with access to:\n"
        "  - `kalshi` — KalshiDataClient instance with methods:\n"
        "      kalshi.search_series(query) — search series by keyword\n"
        "      kalshi.get_events(limit=20, category=None, series_ticker=None) — browse events with nested markets\n"
        "      kalshi.get_markets(limit=20, category=None, series_ticker=None) — list markets\n"
        "      kalshi.get_market(ticker) — get single market detail\n"
        "      kalshi.get_orderbook(ticker) — bid/ask depth\n"
        "      kalshi.get_market_history(ticker, limit=50) — recent trades\n"
        "  - `trader` — PaperTrader instance with methods:\n"
        "      trader.get_portfolio() — returns Portfolio with .balance_cents, .positions, .realized_pnl_cents, .total_value_cents, .total_pnl_cents\n"
        "      trader.get_trade_history(limit=50) — your past trades\n"
        "      trader.db.get_theses(status=None, limit=50) — query theses\n\n"
        "Only print() output is returned. Use print() to show results you want to see.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Use print() for output.",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "place_trade",
        "description": "Place a paper trade. Specify the market ticker, side (yes/no), action (buy/sell), quantity (number of contracts), and your reasoning for the trade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Market ticker"},
                "side": {
                    "type": "string",
                    "enum": ["yes", "no"],
                    "description": "Which side to trade",
                },
                "action": {
                    "type": "string",
                    "enum": ["buy", "sell"],
                    "description": "Buy or sell",
                },
                "quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Number of contracts",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Your reasoning for this trade",
                },
                "thesis_id": {
                    "type": "string",
                    "description": "Optional thesis ID to link this trade to (from create_thesis)",
                },
            },
            "required": ["ticker", "side", "action", "quantity", "reasoning"],
        },
    },
    {
        "name": "update_journal",
        "description": "Update your free-form trading journal. Use this for cross-cutting notes that don't fit the thesis structure (e.g., 'watching for FOMC minutes Wednesday', strategy observations, category-level notes). This OVERWRITES the previous journal. For position-specific reasoning, use create_thesis / update_thesis instead.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Your journal entry (max ~3000 chars). Keep it concise: Watchlist, Key Research, Strategy Notes.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "create_thesis",
        "description": "Create a new thesis when opening a position. A thesis is a structured record of WHY you're entering a trade — your probability estimate, the market price, and your reasoning. The thesis tracks through the position's lifecycle and is used to evaluate your performance over time. Returns a thesis_id to pass to place_trade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Market ticker"},
                "side_predicted": {
                    "type": "string",
                    "enum": ["yes", "no"],
                    "description": "Which side you believe will win",
                },
                "category": {
                    "type": "string",
                    "description": "Category (Economics, Politics, Tech, Climate, Sports, Financials, etc.)",
                },
                "entry_thesis": {
                    "type": "string",
                    "description": "Why you're entering this position — your reasoning for the probability estimate",
                },
                "probability_estimate": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 99,
                    "description": "Your probability estimate in cents (1-99). E.g., 72 means you think there's a 72% chance.",
                },
                "market_price_at_entry": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 99,
                    "description": "The current market price in cents for the side you're buying",
                },
            },
            "required": ["ticker", "side_predicted", "entry_thesis", "probability_estimate", "market_price_at_entry"],
        },
    },
    {
        "name": "update_thesis",
        "description": "Update an existing thesis — e.g., revise your probability estimate, add notes, or close it with an exit reason. Use close_thesis instead if you're fully exiting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thesis_id": {"type": "string", "description": "The thesis ID to update"},
                "probability_estimate": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 99,
                    "description": "Revised probability estimate",
                },
                "entry_thesis": {
                    "type": "string",
                    "description": "Updated reasoning (appends context to original thesis)",
                },
                "category": {"type": "string", "description": "Updated category"},
            },
            "required": ["thesis_id"],
        },
    },
    {
        "name": "close_thesis",
        "description": "Close a thesis when exiting a position (selling) or when the market settles. Records the outcome and exit reasoning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thesis_id": {"type": "string", "description": "The thesis ID to close"},
                "exit_thesis": {
                    "type": "string",
                    "description": "Why you're exiting — what changed, what you learned",
                },
                "outcome": {
                    "type": "string",
                    "enum": ["win", "loss", "partial"],
                    "description": "How it turned out",
                },
                "realized_pnl_cents": {
                    "type": "integer",
                    "description": "Realized P&L in cents for this thesis",
                },
            },
            "required": ["thesis_id", "exit_thesis", "outcome"],
        },
    },
    {
        "name": "get_theses",
        "description": "Get your theses. Filter by status to see active positions, or all to review your track record.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "closed", "settled"],
                    "description": "Filter by status (omit for all)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                },
            },
        },
    },
]

RESEARCH_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for information relevant to a prediction market. Use this to research events, check recent news, find data that could inform your trading decisions. Returns titles, URLs, and snippets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — be specific about what you want to learn",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "news_search",
        "description": "Search recent news articles. Use this for time-sensitive markets where current events matter (elections, economic data, policy decisions, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "News search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_webpage",
        "description": "Read the full text content of a webpage. Use this to dive deeper into a search result — read the full article, report, or analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to read",
                },
            },
            "required": ["url"],
        },
    },
]


def get_tools() -> list:
    tools = list(MARKET_TOOLS)
    if config.ENABLE_WEB_RESEARCH:
        tools.extend(RESEARCH_TOOLS)
    if tools:
        tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}
    return tools


class ToolDispatcher:
    def __init__(self, kalshi_client: KalshiDataClient, paper_trader: PaperTrader, session_id: str):
        self.kalshi = kalshi_client
        self.trader = paper_trader
        self.session_id = session_id
        self._researcher = None

    @property
    def researcher(self):
        if self._researcher is None:
            from agent.research import WebResearcher
            self._researcher = WebResearcher()
        return self._researcher

    def dispatch(self, tool_name: str, tool_input: dict) -> tuple:
        """Dispatch a tool call.

        Returns (content_str, raw) where content_str is what the model sees
        and raw is the underlying dict/list/str for structural inspection.
        """
        try:
            handler = getattr(self, f"_handle_{tool_name}", None)
            if not handler:
                raw = {"error": f"Unknown tool: {tool_name}"}
                return json.dumps(raw), raw
            result = handler(tool_input)
            if isinstance(result, str):
                return result, result
            return json.dumps(result, default=str), result
        except Exception as e:
            raw = {"error": str(e)}
            return json.dumps(raw), raw

    # --- Code execution ---

    def _handle_run_python(self, inp: dict) -> str:
        from agent.sandbox import run_python
        return run_python(inp["code"])

    def _handle_place_trade(self, inp: dict) -> dict:
        trade = self.trader.place_trade(
            ticker=inp["ticker"],
            side=inp["side"],
            action=inp["action"],
            quantity=inp["quantity"],
            reasoning=inp.get("reasoning", ""),
            session_id=self.session_id,
            thesis_id=inp.get("thesis_id", ""),
        )
        return {
            "status": "filled",
            "trade_id": trade.id,
            "ticker": trade.ticker,
            "side": trade.side,
            "action": trade.action,
            "quantity": trade.quantity,
            "price_dollars": f"${trade.price_cents / 100:.2f}",
            "total_cost_dollars": f"${trade.total_cost_cents / 100:.2f}",
            "thesis_id": trade.thesis_id or None,
        }


    def _handle_update_journal(self, inp: dict) -> dict:
        from agent.journal import write_journal
        write_journal(inp["content"])
        return {"status": "saved", "chars": len(inp["content"])}

    # --- Thesis tools ---

    def _handle_create_thesis(self, inp: dict) -> dict:
        import uuid as _uuid
        from datetime import datetime, timezone
        from engine.models import Thesis

        thesis_id = str(_uuid.uuid4())[:12]
        prob = inp["probability_estimate"]
        market_price = inp["market_price_at_entry"]

        thesis = Thesis(
            id=thesis_id,
            ticker=inp["ticker"],
            side_predicted=inp["side_predicted"],
            category=inp.get("category", ""),
            entry_thesis=inp["entry_thesis"],
            probability_estimate=prob,
            market_price_at_entry=market_price,
            edge_cents=prob - market_price,
            status="active",
            created_at=datetime.now(timezone.utc),
            session_id=self.session_id,
        )
        self.trader.db.save_thesis(thesis)
        return {
            "status": "created",
            "thesis_id": thesis_id,
            "edge_cents": thesis.edge_cents,
            "message": f"Thesis created. Use thesis_id='{thesis_id}' when placing trades for this position.",
        }

    def _handle_update_thesis(self, inp: dict) -> dict:
        thesis_id = inp["thesis_id"]
        thesis = self.trader.db.get_thesis(thesis_id)
        if not thesis:
            return {"error": f"Thesis {thesis_id} not found"}

        updates = {}
        if "probability_estimate" in inp:
            updates["probability_estimate"] = inp["probability_estimate"]
        if "entry_thesis" in inp:
            updates["entry_thesis"] = inp["entry_thesis"]
        if "category" in inp:
            updates["category"] = inp["category"]

        self.trader.db.update_thesis(thesis_id, **updates)
        return {"status": "updated", "thesis_id": thesis_id, "fields_updated": list(updates.keys())}

    def _handle_close_thesis(self, inp: dict) -> dict:
        from datetime import datetime, timezone

        thesis_id = inp["thesis_id"]
        thesis = self.trader.db.get_thesis(thesis_id)
        if not thesis:
            return {"error": f"Thesis {thesis_id} not found"}
        if thesis.status != "active":
            return {"error": f"Thesis {thesis_id} is already {thesis.status}"}

        self.trader.db.update_thesis(
            thesis_id,
            status="closed",
            exit_thesis=inp["exit_thesis"],
            outcome=inp["outcome"],
            realized_pnl_cents=inp.get("realized_pnl_cents", 0),
            closed_at=datetime.now(timezone.utc).isoformat(),
        )
        return {
            "status": "closed",
            "thesis_id": thesis_id,
            "outcome": inp["outcome"],
        }

    def _handle_get_theses(self, inp: dict) -> list:
        theses = self.trader.db.get_theses(
            status=inp.get("status"),
            limit=inp.get("limit", 20),
        )
        return [
            {
                "id": t.id,
                "ticker": t.ticker,
                "side_predicted": t.side_predicted,
                "category": t.category,
                "entry_thesis": t.entry_thesis[:200],
                "probability_estimate": t.probability_estimate,
                "market_price_at_entry": t.market_price_at_entry,
                "edge_cents": t.edge_cents,
                "status": t.status,
                "outcome": t.outcome,
                "realized_pnl_cents": t.realized_pnl_cents,
                "created_at": t.created_at.isoformat(),
            }
            for t in theses
        ]

    # --- Research tools ---

    def _handle_web_search(self, inp: dict) -> list:
        return self.researcher.search(
            query=inp["query"],
            max_results=min(inp.get("max_results", 5), 10),
        )

    def _handle_news_search(self, inp: dict) -> list:
        return self.researcher.search_news(
            query=inp["query"],
            max_results=min(inp.get("max_results", 5), 10),
        )

    def _handle_read_webpage(self, inp: dict) -> dict:
        return self.researcher.read_webpage(url=inp["url"])
