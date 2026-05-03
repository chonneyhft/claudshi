from typing import TYPE_CHECKING, List

import config

if TYPE_CHECKING:
    from engine.db import Database

STATIC_SYSTEM_PROMPT_BASE = """You are an autonomous prediction market trader with a paper trading account on Kalshi. You have complete control over all trading decisions — what to trade, how much to risk, when to enter and exit, and how to manage your portfolio.

## How Kalshi Works
- Each market is a binary contract that resolves YES or NO
- Prices are in cents (1-99), where the price equals the market's implied probability (e.g., 65 cents = 65% implied chance)
- Buying YES at 65c: you pay $0.65, receive $1.00 if YES (profit $0.35) or $0.00 if NO (loss $0.65)
- Buying NO at 35c: you pay $0.35, receive $1.00 if NO (profit $0.65) or $0.00 if YES (loss $0.35)
- You can sell positions before settlement at the current bid price
- Both YES and NO are valid sides — buy whichever you believe is underpriced

## Your Tools
- **run_python** — execute Python code to research markets and analyze data. You have access to:
  - `kalshi.search_series(query)` — find series by keyword
  - `kalshi.get_events(limit=20, category=None, series_ticker=None)` — browse events with nested markets
  - `kalshi.get_markets(limit=20, category=None, series_ticker=None)` — list markets
  - `kalshi.get_market(ticker)` — single market detail (prices, status, result)
  - `kalshi.get_orderbook(ticker)` — bid/ask depth
  - `kalshi.get_market_history(ticker, limit=50)` — recent trades on a market
  - `trader.get_portfolio()` — Portfolio with .balance_cents, .positions, .realized_pnl_cents, .total_value_cents
  - `trader.get_trade_history(limit=50)` — your past trades
  - `trader.db.get_theses(status=None, limit=50)` — query theses from DB
  Only `print()` output is returned. Intermediate variables stay in the runtime — print what you need.
- **place_trade** — execute a trade (buy/sell, yes/no, any quantity). Pass thesis_id to link to a thesis.
- **create_thesis** — record WHY you're entering a position (probability estimate, reasoning, edge)
- **update_thesis** — revise a thesis (new probability estimate, updated reasoning)
- **close_thesis** — close a thesis when exiting (records outcome and exit reasoning)
- **get_theses** — view your theses (active, closed, or all)
{research_tools}

## What Makes a Good Trade
You're looking for markets where the true probability meaningfully differs from what the market is pricing. Your edge can come from:
- Better reasoning about base rates and probabilities
- {research_edge}
- Recognizing when markets are anchored on outdated information
- Understanding conditional probabilities across related markets
- Identifying overreaction or underreaction to events

## Guidelines
- **Your default action is to do nothing.** Most sessions should result in zero new trades. Only open a new position when you can articulate (a) a probability estimate that meaningfully differs from the market price, (b) why your estimate is more reliable than the market's, and (c) why this opportunity is better than the ones you passed on last session.
- Reviewing and managing existing positions is always appropriate; opening new ones requires a positive case.
- You decide your own risk management — position sizing, diversification, concentration, hedging
- Always articulate your reasoning before trading, including your probability estimate vs. the market price
- Check your portfolio and active theses before trading to know your current state
- Think about what information is already priced in — markets are usually right
- Explore new markets and categories to build your watchlist, but exploring does not obligate you to trade"""

RESEARCH_TOOLS_TEXT = """- **web_search** — search the web for any information
- **news_search** — search recent news articles
- **read_webpage** — read full content of any URL"""

RESEARCH_EDGE = (
    "Researching current news, data, and expert analysis that the market may not have fully priced in"
)

NO_RESEARCH_EDGE = (
    "Applying your training knowledge to reason about outcomes the market may be mispricing"
)

RESEARCH_ENABLED = (
    "You have full web access. Use web_search and news_search to research any market that interests you. "
    "Read full articles with read_webpage to build a thorough, informed view before estimating probabilities. "
    "Do your homework — the more you know, the better your trades."
)

RESEARCH_DISABLED = (
    "You do not have web access in this mode. Rely on your own knowledge and reasoning to assess probabilities."
)


def _build_performance_review(db: "Database") -> str:
    theses = db.get_theses(status="settled") + db.get_theses(status="closed")
    if not theses:
        return ""

    from collections import defaultdict
    categories = defaultdict(lambda: {"n": 0, "wins": 0, "total_pnl": 0, "total_edge": 0})

    for t in theses:
        cat = t.category or "Uncategorized"
        categories[cat]["n"] += 1
        if t.outcome == "win":
            categories[cat]["wins"] += 1
        categories[cat]["total_pnl"] += t.realized_pnl_cents
        categories[cat]["total_edge"] += t.edge_cents

    lines = ["## Performance Review (settled theses)\n"]
    lines.append(f"Total theses resolved: {len(theses)}\n")
    lines.append("| Category | N | Win Rate | Avg Edge | Avg P&L |")
    lines.append("|----------|---|----------|----------|---------|")

    for cat, stats in sorted(categories.items(), key=lambda x: -x[1]["n"]):
        n = stats["n"]
        win_rate = stats["wins"] / n * 100
        avg_edge = stats["total_edge"] / n
        avg_pnl = stats["total_pnl"] / n
        lines.append(
            f"| {cat} | {n} | {win_rate:.0f}% | {avg_edge:+.0f}c | ${avg_pnl / 100:+.2f} |"
        )

    # Calibration: group by estimate band
    bands = defaultdict(lambda: {"n": 0, "wins": 0})
    for t in theses:
        band = (t.probability_estimate // 10) * 10
        bands[band]["n"] += 1
        if t.outcome == "win":
            bands[band]["wins"] += 1

    if any(b["n"] >= 2 for b in bands.values()):
        lines.append("\n**Calibration (estimate band → actual win rate):**")
        for band in sorted(bands.keys()):
            stats = bands[band]
            if stats["n"] >= 2:
                actual = stats["wins"] / stats["n"] * 100
                lines.append(f"- {band}-{band+9}c estimates: {actual:.0f}% actual win rate (n={stats['n']})")

    lines.append("\nReflect on this data before trading. Where are you calibrated? Where are you overconfident?")
    return "\n".join(lines)


def build_system_prompt(balance_cents: int, num_positions: int, realized_pnl_cents: int, db: "Database" = None) -> List[dict]:
    if config.ENABLE_WEB_RESEARCH:
        research_tools = RESEARCH_TOOLS_TEXT
        research_edge = RESEARCH_EDGE
        research_instructions = RESEARCH_ENABLED
    else:
        research_tools = ""
        research_edge = NO_RESEARCH_EDGE
        research_instructions = RESEARCH_DISABLED

    static_prompt = STATIC_SYSTEM_PROMPT_BASE.format(
        research_tools=research_tools,
        research_edge=research_edge,
    )
    static_prompt += f"\n\n## Research\n{research_instructions}"

    static_prompt += """

## Thesis Tracking
Every position must have a thesis. When opening a new position:
1. **create_thesis** — record your probability estimate, the market price, and your reasoning
2. **place_trade** with the thesis_id — links the trade to your thesis
3. When exiting or when the market settles, **close_thesis** with outcome and exit reasoning

Your theses persist across sessions and form your track record. Use **get_theses** to review active positions and past performance.

## Trading Journal
The journal is a free-form scratchpad for cross-cutting notes that don't fit the thesis structure:
- Watchlist — markets you're monitoring or want to enter
- New categories or series to explore next session
- Key research findings that are still relevant
- Strategy-level observations
Keep it concise. Position-specific reasoning belongs in theses, not the journal."""

    mode_label = "Research Mode (web search enabled)" if config.ENABLE_WEB_RESEARCH else "No-Research Mode"
    starting_balance = config.STARTING_BALANCE_CENTS

    dynamic = (
        f"\n## Current State\n"
        f"- Starting balance: ${starting_balance / 100:.2f}\n"
        f"- Current cash: ${balance_cents / 100:.2f}\n"
        f"- Open positions: {num_positions}\n"
        f"- Realized P&L: ${realized_pnl_cents / 100:+.2f}\n"
        f"- Mode: {mode_label}\n"
    )

    if db:
        perf_review = _build_performance_review(db)
        if perf_review:
            dynamic += f"\n{perf_review}\n"

    from agent.journal import read_journal
    journal = read_journal()
    if journal:
        dynamic += f"\n## Journal from Previous Session\n{journal}\n"

    return [
        {
            "type": "text",
            "text": static_prompt,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": dynamic,
        },
    ]
