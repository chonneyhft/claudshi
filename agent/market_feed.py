from typing import List

import config
from kalshi.client import KalshiDataClient


def build_market_feed(kalshi: KalshiDataClient, held_tickers: List[str] = None) -> str:
    held_tickers = set(held_tickers or [])
    seen_tickers = set()
    sections = []

    position_markets = _fetch_position_markets(kalshi, held_tickers, seen_tickers)
    if position_markets:
        sections.append(("Your Positions — Current Prices", position_markets))

    watchlist_markets = _fetch_watchlist_markets(kalshi, seen_tickers)
    if watchlist_markets:
        sections.append(("Watchlist Series", watchlist_markets))

    trending_markets = _fetch_trending_markets(kalshi, seen_tickers)
    if trending_markets:
        sections.append(("Trending Markets (by volume)", trending_markets))

    if not sections:
        return ""

    lines = ["## Market Feed\n"]
    for heading, markets in sections:
        lines.append(f"### {heading}")
        lines.append("| Ticker | Title | Yes Bid/Ask | No Bid/Ask | Volume | OI | Close |")
        lines.append("|--------|-------|-------------|------------|--------|----|-------|")
        for m in markets:
            yes = f"{m['yes_bid'] or '-'}/{m['yes_ask'] or '-'}"
            no = f"{m['no_bid'] or '-'}/{m['no_ask'] or '-'}"
            lines.append(
                f"| {m['ticker']} | {m['title'][:55]} | {yes} | {no} "
                f"| {_fmt_num(m['volume'])} | {_fmt_num(m['oi'])} | {m['close'][:10]} |"
            )
        lines.append("")

    return "\n".join(lines)


def _fetch_position_markets(
    kalshi: KalshiDataClient, held_tickers: set, seen: set
) -> list:
    markets = []
    for ticker in held_tickers:
        try:
            m = kalshi.get_market(ticker)
            if m and m.get("ticker"):
                markets.append(_to_row(m))
                seen.add(ticker)
        except Exception:
            continue
    return markets


def _fetch_watchlist_markets(kalshi: KalshiDataClient, seen: set) -> list:
    markets = []
    for series in config.WATCHED_SERIES:
        try:
            raw = kalshi.get_markets(limit=10, series_ticker=series)
            for m in raw:
                ticker = m.get("ticker", "")
                if ticker and ticker not in seen and m.get("status") in ("open", "active"):
                    markets.append(_to_row(m))
                    seen.add(ticker)
        except Exception:
            continue
    markets.sort(key=lambda x: x["volume"], reverse=True)
    return markets[:20]


def _fetch_trending_markets(kalshi: KalshiDataClient, seen: set) -> list:
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    all_markets = []
    try:
        events = kalshi.get_events(limit=50, with_nested_markets=True)
        for e in events:
            cat = e.get("category", "")
            for m in e.get("markets", []):
                ticker = m.get("ticker", "")
                vol = _parse_num(m.get("volume"))
                close = m.get("close_time", "")
                if (
                    ticker
                    and ticker not in seen
                    and vol > 500
                    and m.get("status") in ("open", "active")
                    and "KXMVE" not in ticker
                    and close
                    and close < cutoff
                ):
                    row = _to_row(m)
                    row["category"] = cat
                    all_markets.append(row)
                    seen.add(ticker)
    except Exception:
        pass

    all_markets.sort(key=lambda x: x["volume"], reverse=True)
    return all_markets[:15]


def _to_row(m: dict) -> dict:
    return {
        "ticker": m.get("ticker", ""),
        "title": m.get("title", ""),
        "yes_bid": m.get("yes_bid"),
        "yes_ask": m.get("yes_ask"),
        "no_bid": m.get("no_bid"),
        "no_ask": m.get("no_ask"),
        "volume": _parse_num(m.get("volume") or m.get("open_interest", 0)),
        "oi": _parse_num(m.get("open_interest", 0)),
        "close": m.get("close_time", ""),
    }


def _parse_num(val) -> float:
    try:
        return float(val or 0)
    except (ValueError, TypeError):
        return 0.0


def _fmt_num(val: float) -> str:
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"{val / 1_000:.1f}K"
    return str(int(val))
