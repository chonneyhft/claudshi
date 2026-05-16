# claudshi

An autonomous prediction market trading agent powered by Claude. It researches markets, forms probabilistic views, and executes paper trades on Kalshi — running in a loop with no human intervention.

## How it works

Claude operates as an agentic loop with tool use. Each session it:

1. Reviews its current portfolio and P&L
2. Researches active markets using web search
3. Forms probabilistic assessments and identifies edges
4. Executes trades via a paper trading engine
5. Logs reasoning for every decision

The agent uses Claude Opus as its backbone and runs on a configurable interval (default: 6 hours).

## Architecture

```
main.py              CLI entrypoint (run / loop / dashboard / settle / status)
agent/
  harness.py         Agentic loop with tool use
  tools.py           Tool definitions (market lookup, trade, research)
  prompts.py         System prompt construction
  research.py        Web research utilities
  journal.py         Decision journaling
engine/
  paper_trader.py    Paper trading engine with position tracking
  db.py              SQLite persistence via DuckDB
  models.py          Pydantic models for trades/portfolio
kalshi/
  client.py          Kalshi API client for market data
scheduler/
  runner.py          APScheduler-based trading loop
dashboard/
  app.py             Streamlit dashboard (legacy)
api/
  server.py          FastAPI read-only data layer for the web UI
web/                 Vite + React + TypeScript dashboard
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

## Usage

```bash
# Run a single trading session
python main.py run

# Run with a custom prompt
python main.py run --prompt "Focus on climate markets today"

# Start the scheduled loop (default: every 6 hours)
python main.py loop

# Check portfolio status
python main.py status

# Settle expired positions
python main.py settle

# Launch the legacy Streamlit dashboard
python main.py dashboard

# Launch the new web dashboard (FastAPI + Vite/React on :8000 and :5173)
./scripts/dev_web.sh
```

## Configuration

Edit `config.py` or set environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required. Your Anthropic API key |
| `ENABLE_WEB_RESEARCH` | `true` | Toggle web research capability |
| `BRAVE_API_KEY` | — | Optional. For Brave Search (falls back to DuckDuckGo) |

## License

MIT
