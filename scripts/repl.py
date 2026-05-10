"""Pre-imported analysis REPL for Claude Code.

Run via Bash with code piped or passed inline:
    python scripts/repl.py -c 'print(trader.get_portfolio().balance_cents)'
    echo 'for m in kalshi.get_markets(limit=5): print(m["ticker"])' | python scripts/repl.py

`kalshi` and `trader` are bound in the exec namespace. Use print() for output.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from engine.db import Database
from engine.paper_trader import PaperTrader
from kalshi.client import KalshiDataClient


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--code", help="Python source to execute. Omit to read from stdin.")
    args = ap.parse_args()

    src = args.code if args.code is not None else sys.stdin.read()
    if not src.strip():
        print("repl.py: no code provided", file=sys.stderr)
        return 2

    kalshi = KalshiDataClient()
    db = Database(config.DB_PATH)
    trader = PaperTrader(db, kalshi)
    ns = {"kalshi": kalshi, "trader": trader, "db": db}
    exec(compile(src, "<repl>", "exec"), ns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
