import signal
import sys
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler

import config
from agent.harness import AgentHarness
from agent.logger import DecisionLogger
from agent.tools import ToolDispatcher
from engine.db import Database
from engine.paper_trader import PaperTrader
from kalshi.client import KalshiDataClient


class TradingRunner:
    def __init__(self):
        self.kalshi = KalshiDataClient()
        self.db = Database(config.DB_PATH)
        self.trader = PaperTrader(self.db, self.kalshi)

    def run_once(self, prompt: Optional[str] = None) -> dict:
        settled = self.trader.settle_positions()
        if settled:
            print(f"Settled {len(settled)} position(s)")
            for t in settled:
                print(f"  {t.ticker}: {t.side} -> ${t.price_cents / 100:.2f} ({t.reasoning})")

        logger = DecisionLogger()
        dispatcher = ToolDispatcher(self.kalshi, self.trader, logger.session_id)
        harness = AgentHarness(self.trader, dispatcher, logger)

        msg = prompt or "Analyze the markets and make trading decisions."
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting session {logger.session_id}...")

        summary = harness.run_session(msg)

        print(f"Session {summary['session_id']} complete:")
        print(f"  Turns: {summary['turns']}")
        print(f"  Trades: {summary['trades_made']}")
        print(f"  Portfolio: {summary['portfolio_value']}")
        print(f"  P&L: {summary['total_pnl']}")
        print(f"  Tokens: {summary['total_input_tokens']} in / {summary['total_output_tokens']} out")
        return summary

    def run_scheduled(self, interval_seconds: Optional[int] = None):
        interval = interval_seconds or config.TRADING_INTERVAL_SECONDS
        print(f"Starting scheduled trading loop (interval: {interval}s)")
        print("Press Ctrl+C to stop\n")

        self.run_once()

        scheduler = BlockingScheduler()
        scheduler.add_job(self.run_once, "interval", seconds=interval)

        def shutdown(signum, frame):
            print("\nShutting down scheduler...")
            scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        scheduler.start()

    def get_status(self) -> str:
        portfolio = self.trader.get_portfolio()
        lines = [
            "=== Portfolio Status ===",
            f"Cash: ${portfolio.balance_cents / 100:.2f}",
            f"Total Value: ${portfolio.total_value_cents / 100:.2f}",
            f"Realized P&L: ${portfolio.realized_pnl_cents / 100:+.2f}",
            f"Unrealized P&L: ${portfolio.unrealized_pnl_cents / 100:+.2f}",
            f"Total P&L: ${portfolio.total_pnl_cents / 100:+.2f}",
            f"Total Trades: {portfolio.total_trades}",
            f"Open Positions: {len(portfolio.positions)}",
        ]
        if portfolio.positions:
            lines.append("\n--- Positions ---")
            for p in portfolio.positions:
                lines.append(
                    f"  {p.ticker} ({p.side}) x{p.quantity} "
                    f"@ ${p.avg_price_cents / 100:.2f} "
                    f"-> ${p.current_price_cents / 100:.2f} "
                    f"(PnL: ${p.unrealized_pnl_cents / 100:+.2f})"
                )
        return "\n".join(lines)
