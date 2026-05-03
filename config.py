import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

STARTING_BALANCE_CENTS = 10_000_00

TRADING_INTERVAL_SECONDS = 21600
CLAUDE_MODEL = "claude-opus-4-6"
MAX_AGENT_TURNS = 35

ENABLE_WEB_RESEARCH = os.getenv("ENABLE_WEB_RESEARCH", "true").lower() == "true"

MARKET_CATEGORIES = ["economics", "politics", "tech", "climate"]

DB_PATH = str(BASE_DIR / "data" / "trades.db")
LOG_DIR = str(BASE_DIR / "data" / "agent_logs")
