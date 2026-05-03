import argparse
import subprocess
import sys

from scheduler.runner import TradingRunner


def main():
    parser = argparse.ArgumentParser(description="Claude Kalshi Trading Agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a single trading session")
    run_parser.add_argument("--prompt", type=str, help="Custom prompt for Claude")

    loop_parser = subparsers.add_parser("loop", help="Run scheduled trading loop")
    loop_parser.add_argument("--interval", type=int, default=3600, help="Seconds between sessions")

    subparsers.add_parser("dashboard", help="Launch the Streamlit dashboard")

    subparsers.add_parser("settle", help="Settle expired positions")

    subparsers.add_parser("status", help="Print current portfolio status")

    args = parser.parse_args()

    if args.command == "run":
        runner = TradingRunner()
        runner.run_once(prompt=args.prompt)

    elif args.command == "loop":
        runner = TradingRunner()
        runner.run_scheduled(interval_seconds=args.interval)

    elif args.command == "dashboard":
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", "dashboard/app.py"],
            check=True,
        )

    elif args.command == "settle":
        runner = TradingRunner()
        settled = runner.trader.settle_positions()
        if settled:
            print(f"Settled {len(settled)} position(s):")
            for t in settled:
                print(f"  {t.ticker}: ${t.price_cents / 100:.2f} ({t.reasoning})")
        else:
            print("No positions to settle.")

    elif args.command == "status":
        runner = TradingRunner()
        print(runner.get_status())

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
