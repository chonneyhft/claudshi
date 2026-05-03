import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from engine.db import Database

st.set_page_config(
    page_title="Claudshi Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    [data-testid="stMetric"] {
        background-color: #0e1117;
        border: 1px solid #1e2530;
        border-radius: 8px;
        padding: 12px 16px;
    }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; }
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
    .trade-buy { color: #00c853; }
    .trade-sell { color: #ff5252; }
    .session-header { font-size: 0.9rem; color: #888; }
    div[data-testid="stExpander"] details summary span { font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    return Database(config.DB_PATH)


def load_logs():
    log_dir = Path(config.LOG_DIR)
    if not log_dir.exists():
        return []
    sessions = []
    for log_file in sorted(log_dir.glob("*.jsonl"), reverse=True):
        entries = []
        for line in log_file.read_text().strip().split("\n"):
            if line:
                entries.append(json.loads(line))
        if entries:
            sessions.append(entries)
    return sessions


def fmt_dollars(cents):
    return f"${cents / 100:,.2f}"


def fmt_pnl(cents):
    val = f"${cents / 100:+,.2f}"
    return val


db = get_db()

# ─── Sidebar ───
with st.sidebar:
    st.markdown("## Claudshi")
    st.markdown("*Claude Prediction Market Trader*")
    st.divider()

    balance, realized_pnl = db.get_portfolio_state()
    positions = db.get_positions()
    trades = db.get_trades(limit=10000)
    snapshots = db.get_snapshots()
    sessions = load_logs()

    starting = config.STARTING_BALANCE_CENTS
    cost_basis = sum(p.avg_price_cents * p.quantity for p in positions)
    if snapshots:
        latest = snapshots[-1]
        positions_value = latest.positions_value_cents
        total_value = latest.total_value_cents
    else:
        positions_value = cost_basis
        total_value = balance + positions_value
    total_pnl = total_value - starting
    pct_return = (total_pnl / starting) * 100 if starting else 0

    st.metric("Portfolio Value", fmt_dollars(total_value), f"{pct_return:+.1f}%")
    st.metric("Cash", fmt_dollars(balance))
    st.metric("Invested", fmt_dollars(positions_value))

    st.divider()
    st.markdown(f"**Trades:** {len(trades)}")
    st.markdown(f"**Open Positions:** {len(positions)}")
    st.markdown(f"**Sessions:** {len(sessions)}")

    st.divider()
    mode = "Research" if config.ENABLE_WEB_RESEARCH else "No-Research"
    st.markdown(f"**Mode:** {mode}")
    st.markdown(f"**Model:** {config.CLAUDE_MODEL}")
    st.markdown(f"**Interval:** {config.TRADING_INTERVAL_SECONDS // 3600}h")

    if st.button("Refresh Data"):
        st.cache_resource.clear()
        st.rerun()


# ─── Main Content ───
tab_portfolio, tab_chart, tab_trades, tab_sessions, tab_perf = st.tabs([
    "Portfolio", "P&L Chart", "Trade Log", "Agent Sessions", "Performance"
])

# ━━━ Portfolio ━━━
with tab_portfolio:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Value", fmt_dollars(total_value))
    col2.metric("Cash", fmt_dollars(balance))
    col3.metric("Invested", fmt_dollars(positions_value))
    col4.metric("Realized P&L", fmt_pnl(realized_pnl))
    unrealized_pnl = total_value - balance - cost_basis
    col5.metric("Total P&L", fmt_pnl(total_pnl))

    st.divider()

    if positions:
        st.subheader("Open Positions")
        pos_rows = []
        for p in positions:
            cost = p.avg_price_cents * p.quantity
            pos_rows.append({
                "Market": p.ticker,
                "Side": p.side.upper(),
                "Contracts": p.quantity,
                "Entry Price": f"${p.avg_price_cents / 100:.2f}",
                "Cost Basis": fmt_dollars(cost),
                "Max Payout": fmt_dollars(p.quantity * 100),
                "Max Profit": fmt_dollars(p.quantity * 100 - cost),
                "Opened": p.opened_at.strftime("%Y-%m-%d %H:%M"),
            })
        st.dataframe(pos_rows, use_container_width=True, hide_index=True)

        st.subheader("Exposure Breakdown")
        exposure_data = pd.DataFrame([
            {"Category": "Cash (available)", "Amount": balance / 100},
        ] + [
            {"Category": f"{p.ticker} ({p.side.upper()})", "Amount": (p.avg_price_cents * p.quantity) / 100}
            for p in positions
        ])
        st.bar_chart(exposure_data.set_index("Category"), horizontal=True)
    else:
        st.info("No open positions. Claude hasn't placed any trades yet.")

    if trades:
        recent = trades[:5]
        st.subheader("Recent Trades")
        for t in recent:
            action_color = "🟢" if t.action == "buy" else ("🔴" if t.action == "sell" else "⚪")
            st.markdown(
                f"{action_color} **{t.action.upper()} {t.side.upper()}** {t.ticker} "
                f"x{t.quantity} @ ${t.price_cents/100:.2f} = {fmt_dollars(t.total_cost_cents)} "
                f"— *{t.timestamp.strftime('%b %d %H:%M')}*"
            )
            if t.reasoning:
                st.caption(t.reasoning[:200])


# ━━━ P&L Chart ━━━
with tab_chart:
    if snapshots:
        chart_df = pd.DataFrame([
            {
                "Time": s.timestamp,
                "Total Value": s.total_value_cents / 100,
                "Cash": s.balance_cents / 100,
                "Positions": s.positions_value_cents / 100,
            }
            for s in snapshots
        ])
        chart_df = chart_df.set_index("Time")

        st.subheader("Portfolio Value Over Time")
        st.line_chart(chart_df[["Total Value"]], color=["#00c853"])

        st.subheader("Cash vs Positions")
        st.area_chart(chart_df[["Cash", "Positions"]], color=["#42a5f5", "#ff9800"])

        col1, col2, col3 = st.columns(3)
        current_val = snapshots[-1].total_value_cents / 100
        start_val = starting / 100
        col1.metric("Starting Balance", f"${start_val:,.2f}")
        col2.metric("Current Value", f"${current_val:,.2f}")
        col3.metric("Return", f"${current_val - start_val:+,.2f}", f"{pct_return:+.1f}%")

        pnl_df = pd.DataFrame([
            {
                "Time": s.timestamp,
                "Realized P&L": s.realized_pnl_cents / 100,
                "Unrealized P&L": s.unrealized_pnl_cents / 100,
            }
            for s in snapshots
        ])
        pnl_df = pnl_df.set_index("Time")

        st.subheader("P&L Breakdown")
        st.line_chart(pnl_df, color=["#00c853", "#ffab40"])
    else:
        st.info("No data yet. Run a trading session to start tracking.")


# ━━━ Trade Log ━━━
with tab_trades:
    if trades:
        st.subheader(f"All Trades ({len(trades)})")

        trade_rows = []
        for t in trades:
            trade_rows.append({
                "Time": t.timestamp.strftime("%Y-%m-%d %H:%M"),
                "Action": f"{t.action.upper()}",
                "Side": t.side.upper(),
                "Market": t.ticker,
                "Title": t.market_title[:60] if t.market_title else "",
                "Contracts": t.quantity,
                "Price": f"${t.price_cents / 100:.2f}",
                "Total": fmt_dollars(t.total_cost_cents),
                "Session": t.session_id[:8] if t.session_id else "",
            })

        st.dataframe(trade_rows, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Trade Reasoning")
        for t in trades:
            if t.reasoning:
                action_icon = "🟢" if t.action == "buy" else ("🔴" if t.action == "sell" else "⚪")
                with st.expander(
                    f"{action_icon} {t.action.upper()} {t.side.upper()} {t.ticker} x{t.quantity} "
                    f"@ ${t.price_cents/100:.2f} — {t.timestamp.strftime('%b %d %H:%M')}"
                ):
                    st.markdown(t.reasoning)
    else:
        st.info("No trades yet.")


# ━━━ Agent Sessions ━━━
with tab_sessions:
    if sessions:
        st.subheader(f"Trading Sessions ({len(sessions)})")

        for session_entries in sessions:
            session_id = session_entries[0].get("session_id", "?")
            ts = session_entries[0].get("timestamp", "")[:19]

            summary = next((e for e in session_entries if e.get("type") == "session_summary"), None)
            assistant_turns = [e for e in session_entries if e.get("role") == "assistant"]
            tool_result_turns = [e for e in session_entries if e.get("role") == "tool_results"]

            total_tools = sum(
                len(e.get("tool_calls", []) or [])
                for e in assistant_turns
            )

            token_entries = [e for e in session_entries if e.get("token_usage")]
            total_in = sum(e["token_usage"].get("input_tokens", 0) for e in token_entries)
            total_out = sum(e["token_usage"].get("output_tokens", 0) for e in token_entries)
            est_cost = (total_in * 15 + total_out * 75) / 1_000_000

            trades_made = summary.get("trades_made", 0) if summary else 0
            portfolio_val = summary.get("portfolio_value_dollars", "N/A") if summary else "N/A"

            header = (
                f"Session {session_id} — {ts} | "
                f"Trades: {trades_made} | "
                f"Tools: {total_tools} | "
                f"Cost: ${est_cost:.2f} | "
                f"Portfolio: {portfolio_val}"
            )

            with st.expander(header, expanded=(sessions.index(session_entries) == 0)):
                # Session metrics
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Turns", len(assistant_turns))
                m2.metric("Tool Calls", total_tools)
                m3.metric("Trades", trades_made)
                m4.metric("Tokens", f"{(total_in + total_out):,}")
                m5.metric("Est. Cost", f"${est_cost:.2f}")

                st.divider()

                # Turn-by-turn reasoning
                for entry in session_entries:
                    if entry.get("type") == "session_summary":
                        continue

                    role = entry.get("role", "")
                    turn = entry.get("turn", "")

                    if role == "assistant":
                        text = entry.get("content_text", "")
                        tool_calls = entry.get("tool_calls", []) or []

                        if text:
                            st.markdown(f"**Turn {turn} — Claude's thinking:**")
                            st.markdown(text[:1500])

                        if tool_calls:
                            tool_summary = ", ".join(
                                f"`{tc['name']}`" for tc in tool_calls
                            )
                            st.markdown(f"**Tools called:** {tool_summary}")

                            for tc in tool_calls:
                                inp_str = json.dumps(tc.get("input", {}))
                                if len(inp_str) > 150:
                                    inp_str = inp_str[:150] + "..."
                                st.code(f"{tc['name']}({inp_str})", language="text")

                    elif role == "tool_results":
                        results = entry.get("tool_results", []) or []
                        for tr in results:
                            result_preview = tr.get("result", "")[:300]
                            if "error" in result_preview.lower():
                                st.error(f"**{tr['tool_name']}:** {result_preview}")
                            elif tr["tool_name"] == "place_trade":
                                st.success(f"**{tr['tool_name']}:** {result_preview}")
                            else:
                                st.text(f"→ {tr['tool_name']}: {result_preview}")

                    elif role == "error":
                        st.error(f"Error: {entry.get('content_text', '')}")

                if summary:
                    st.divider()
                    st.json(summary)
    else:
        st.info("No sessions yet. Run `python main.py run` to start.")


# ━━━ Performance ━━━
with tab_perf:
    if trades:
        st.subheader("Trading Performance")

        buy_trades = [t for t in trades if t.action == "buy"]
        sell_trades = [t for t in trades if t.action == "sell"]
        settle_trades = [t for t in trades if t.action == "settle"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Trades", len(trades))
        col2.metric("Buys", len(buy_trades))
        col3.metric("Sells", len(sell_trades))
        col4.metric("Settlements", len(settle_trades))

        st.divider()

        # Settlement stats
        if settle_trades:
            st.subheader("Settlement Results")
            wins = [t for t in settle_trades if t.price_cents == 100]
            losses = [t for t in settle_trades if t.price_cents == 0]

            c1, c2, c3 = st.columns(3)
            win_rate = len(wins) / len(settle_trades) * 100
            c1.metric("Win Rate", f"{win_rate:.0f}%")
            c2.metric("Wins", len(wins))
            c3.metric("Losses", len(losses))

            total_won = sum(t.quantity * 100 for t in wins)
            total_cost_wins = sum(t.total_cost_cents for t in wins)
            total_lost = sum(
                next(
                    (bt.total_cost_cents for bt in buy_trades if bt.ticker == t.ticker),
                    0,
                )
                for t in losses
            )
            if wins or losses:
                st.markdown(f"**Gross winnings:** {fmt_dollars(total_won)} from {len(wins)} correct predictions")

        # Capital deployment
        st.subheader("Capital Deployment")
        total_bought = sum(t.total_cost_cents for t in buy_trades)
        total_sold = sum(t.total_cost_cents for t in sell_trades)
        total_settled = sum(t.total_cost_cents for t in settle_trades)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Bought", fmt_dollars(total_bought))
        c2.metric("Total Sold", fmt_dollars(total_sold))
        c3.metric("Total Settled", fmt_dollars(total_settled))

        # Position concentration
        if positions:
            st.subheader("Position Concentration")
            pos_df = pd.DataFrame([
                {
                    "Market": p.ticker,
                    "Cost Basis ($)": (p.avg_price_cents * p.quantity) / 100,
                }
                for p in positions
            ])
            st.bar_chart(pos_df.set_index("Market"))

        # P&L
        st.divider()
        st.subheader("P&L Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Realized P&L", fmt_pnl(realized_pnl))
        c2.metric("Unrealized P&L", fmt_pnl(total_value - balance - cost_basis))
        c3.metric("Total P&L", fmt_pnl(total_pnl))

        # API costs
        st.divider()
        st.subheader("API Costs")
        all_token_entries = []
        log_dir = Path(config.LOG_DIR)
        if log_dir.exists():
            for f in sorted(log_dir.glob("*.jsonl")):
                for line in f.read_text().strip().split("\n"):
                    if line:
                        entry = json.loads(line)
                        if entry.get("token_usage"):
                            all_token_entries.append(entry)

        if all_token_entries:
            total_input = sum(e["token_usage"].get("input_tokens", 0) for e in all_token_entries)
            total_output = sum(e["token_usage"].get("output_tokens", 0) for e in all_token_entries)
            cache_read = sum(e["token_usage"].get("cache_read_input_tokens", 0) for e in all_token_entries)
            cache_write = sum(e["token_usage"].get("cache_creation_input_tokens", 0) for e in all_token_entries)

            est_cost = (total_input * 15 + total_output * 75) / 1_000_000

            c1, c2, c3 = st.columns(3)
            c1.metric("Total API Cost", f"${est_cost:.2f}")
            c2.metric("Input Tokens", f"{total_input:,}")
            c3.metric("Output Tokens", f"{total_output:,}")

            st.caption(
                f"Cache reads: {cache_read:,} | Cache writes: {cache_write:,} | "
                f"Total tokens: {total_input + total_output:,}"
            )

            if len(sessions) > 0:
                avg_cost = est_cost / len(sessions)
                daily_est = avg_cost * 4
                weekly_est = daily_est * 7
                st.markdown(
                    f"**Average per session:** ${avg_cost:.2f} | "
                    f"**Projected daily (4x):** ${daily_est:.2f} | "
                    f"**Projected weekly:** ${weekly_est:.2f}"
                )

        # Trade timeline
        if len(trades) > 1:
            st.divider()
            st.subheader("Trade Timeline")
            timeline_df = pd.DataFrame([
                {
                    "Time": t.timestamp,
                    "Cumulative Trades": i + 1,
                }
                for i, t in enumerate(reversed(trades))
            ])
            timeline_df = timeline_df.set_index("Time")
            st.line_chart(timeline_df)
    else:
        st.info("No trading data yet. Run a session first.")
