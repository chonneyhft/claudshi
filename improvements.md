# Kalshi Agent — Prioritized Improvements

A working doc for the next round of changes to the paper trading harness. Items are ordered by leverage: the things at the top unlock the most downstream value.

---

## 1. Add a `theses` table and link trades to a thesis_id

**Status:** Highest priority. This is the single change that turns the project from "a paper trading bot" into "a system that produces a publishable dataset."

**The problem.** Right now the agent's reasoning lives in two disconnected places: the free-form journal (overwritten every session, ~3000 chars, no structure) and the `reasoning` field on individual trades (per-action, no lifecycle). There's no way to ask "how did my Fed rate decision theses perform versus my election theses" because there's no concept of a thesis as a first-class object. The journal blob is doing triple duty as memory, state, and analytics — and it's bad at all three.

**What to build.** A `theses` table with this rough shape:

```sql
CREATE TABLE theses (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    side_predicted TEXT NOT NULL,           -- yes/no
    category TEXT,                          -- Economics, Politics, etc.
    entry_thesis TEXT NOT NULL,             -- why we're entering
    probability_estimate INTEGER NOT NULL,  -- agent's prob in cents (1-99)
    market_price_at_entry INTEGER NOT NULL, -- the price we paid in cents
    edge_cents INTEGER,                     -- estimate - price (signed)
    status TEXT NOT NULL,                   -- active, closed, settled
    exit_thesis TEXT,                       -- why we exited (or null if settled)
    outcome TEXT,                           -- win, loss, partial
    realized_pnl_cents INTEGER,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    session_id TEXT NOT NULL
);
```

Add a `thesis_id` column to the `trades` table so every trade points to the thesis it belongs to. The agent creates a thesis row when opening a new position. Adds and trims reference the same thesis. The thesis closes when the position is fully exited or settles.

**Why it matters.** Once this exists, you can run queries like:

```sql
SELECT category,
       COUNT(*) as n,
       AVG(probability_estimate - market_price_at_entry) as avg_edge,
       AVG(realized_pnl_cents) as avg_pnl,
       SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as win_rate
FROM theses
WHERE status = 'settled'
GROUP BY category;
```

The agent can read its own track record at the start of each session and the answer to "is this thing working" stops being vibes. This is also the dataset that makes the project credibility-building — a clean (thesis, market price, agent estimate, outcome) record is exactly what's interesting about LLM-driven prediction market trading and what nobody else has cleanly published.

**Tool implications.** Replace `update_journal` as the primary memory mechanism with `create_thesis`, `update_thesis`, and `close_thesis` tools. Keep the journal as a small free-form scratchpad for cross-cutting notes that don't fit the thesis structure ("watching for FOMC minutes Wednesday," etc.).

---

## 2. Wrap `place_trade` in a SQLite transaction

**Status:** Quick safety fix. Do this before anything else can race against it.

**The problem.** `PaperTrader.place_trade` does a read-validate-write across multiple statements:

1. Read current balance (`db.get_portfolio_state`)
2. Validate sufficient balance
3. Save trade (`db.save_trade`)
4. Update balance (`db.update_balance`)
5. Upsert position (`_update_position_buy`)

SQLite with WAL gives reader/writer concurrency but does not make this sequence atomic. If two sessions ever run concurrently — interactive plus scheduled, or two scheduled jobs that overlap — they can both pass the balance check against the same starting balance and both succeed, over-spending the account.

**What to build.** Wrap the trade execution in `BEGIN IMMEDIATE` ... `COMMIT`. `BEGIN IMMEDIATE` (rather than the default deferred) acquires the write lock at the start of the transaction, so the second concurrent attempt blocks until the first completes, then re-reads the balance and either succeeds or fails the validation cleanly.

Sketch:

```python
def place_trade(self, ...):
    with self.db.transaction():  # BEGIN IMMEDIATE ... COMMIT
        balance_cents, _ = self.db.get_portfolio_state()
        # validate
        # save trade, update balance, upsert position — all inside the txn
```

**Why it matters now.** As soon as you add a scheduler, this becomes a real bug, not a theoretical one. Easier to fix while the call site is small.

---

## 3. Migrate read-side tools to a `run_python` code execution pattern

**Status:** Highest-impact architectural change. Save for when items 1 and 2 are done so you don't tangle changes.

**The problem.** A typical session today looks like: `get_portfolio` → `search_series` → `get_events` → `get_market_detail` × 3 → `get_orderbook` × 3 → `place_trade`. That's eight or more round trips through context, with full JSON payloads (events lists, orderbook depth, market metadata) flowing back through the model on every step. Tokens balloon, latency stacks up, and the agent has to navigate a JSON maze instead of thinking about edge.

**What to build.** Expose `KalshiDataClient`, `PaperTrader`, and a few analytics helpers as a Python module mounted into a sandbox. Replace the read-side tools (`search_series`, `get_events`, `get_markets`, `get_market_detail`, `get_orderbook`, `get_portfolio`, `get_trade_history`) with a single `run_python(code: str)` tool that executes in that sandbox.

The agent then writes things like:

```python
portfolio = trader.get_portfolio()
fed_events = kalshi.get_events(series_ticker="FEDDECISION")
candidates = [
    m for e in fed_events for m in e.markets
    if 40 < m.yes_ask < 60 and m.volume > 1000
]
for m in sorted(candidates, key=lambda m: -m.volume)[:5]:
    print(f"{m.ticker} | {m.title} | yes_ask={m.yes_ask} | vol={m.volume}")
```

Only the `print` output flows back into context. Intermediate data structures stay in the runtime.

**Keep `place_trade` (and the new thesis tools) as structured tools.** Code execution is right for read/analyze workflows; structured tools are right for the irreversible actions that move money. The agent should not be able to accidentally write `trader.balance_cents = 999999` in a Python block and have that take effect — keep state-mutating actions behind explicit, validated tool schemas.

**Sandboxing.** For a paper trading project, a subprocess with a restricted environment is fine. If/when this touches real money, use a proper sandbox (Docker, gVisor, Anthropic's code execution tool, etc.). Don't use `exec()` in-process — too easy to clobber state.

**Why it matters.** You'll cut tokens per session by something like 5–10x and the agent's reasoning quality goes up because it's expressing analysis as code instead of as a multi-turn navigation. This is the architectural pattern that makes 2026-style agents feel different from 2024-style agents.

---

## 4. Add a "performance review" mode at session start

**Status:** Builds directly on item 1. Don't do this until the theses table exists.

**The problem.** The current session start is "read journal, look at portfolio, find trades to make." There's no structured reflection on what's been working. The agent has no way to notice "I keep being overconfident on macro markets" or "my political theses have a 30% win rate on a 50-cent average estimate, which means I'm systematically wrong."

**What to build.** A session start sequence that runs before the trading prompt:

1. Query the theses table for all settled theses since last review (or last N theses, whichever is shorter).
2. Compute per-category and per-edge-band performance: win rate, avg P&L, calibration (did 60-cent estimates win 60% of the time?).
3. Surface this as a structured block in the system prompt — not free-form, just a short table the agent has to look at before deciding to trade.
4. Have the agent write a short reflection (one paragraph) on what the data implies for this session before exploring new markets.

**Why it matters.** This is where the feedback loop closes. Without it, you have an agent that trades and a database that records — but no mechanism for the agent to update its own behavior based on outcomes. With it, you have something that can actually improve over time, and the calibration data alone is interesting enough to be the main asset of the project.

---

## 5. Tighten the system prompt to bias toward inaction

**Status:** Easy to implement, meaningful impact. Do alongside item 4.

**The problem.** The current prompt says:

> "There are no preset limits. This is your portfolio to manage as you see fit."

> "Each session, check on your existing positions AND actively explore new markets and categories for fresh opportunities."

These two together push the agent toward action every session. Agents have a known overtrading bias — given the choice between "do something" and "do nothing," they pick "do something" more often than is optimal, because the implicit reward signal is engagement. For prediction markets, where edge is rare and transaction friction is real, overtrading is the default failure mode of any naive trading system, human or otherwise.

**What to build.** Reframe the default. Something like:

> "Your default action is to do nothing. Most sessions should result in zero new trades. Only open a new position when you can articulate (a) a probability estimate that meaningfully differs from the market price, (b) why your estimate is more reliable than the market's, and (c) why this opportunity is better than the ones you passed on last session. Reviewing existing positions is always appropriate; opening new ones requires a positive case."

Combined with the performance review in item 4, this gives the agent both the prior (default to inaction) and the data (here's how you've actually performed) to make better calls.

**Why it matters.** The cheapest way to improve a trading system's results is usually to make it trade less. This is a one-paragraph prompt change that probably moves the needle as much as anything else on this list.

---

## 6. Fix the NO-side mark-to-market fallback

**Status:** Correctness bug. Low urgency until you have NO positions, but easy to fix.

**The problem.** In `PaperTrader.get_portfolio`:

```python
pos.current_price_cents = market.get("no_bid") or (100 - (market.get("last_price") or 0))
```

The `100 - last_price` fallback assumes `last_price` reflects the YES side's last trade. On Kalshi this is usually true, but the field semantics don't guarantee it. If `last_price` ever reflects a NO trade, NO positions get marked at the wrong price, which propagates into unrealized P&L and the snapshots table.

**What to build.** Either pull from the orderbook directly (most accurate) or be explicit about which side the fallback assumes and document it. A safer fallback is:

```python
if pos.side == "no":
    no_bid = market.get("no_bid")
    if no_bid:
        pos.current_price_cents = no_bid
    else:
        # Last resort: use mid-market from orderbook, or hold at avg_price
        pos.current_price_cents = pos.avg_price_cents
```

Marking at avg_price when data is missing is conservative — unrealized P&L shows zero rather than fabricating a number from a possibly-wrong assumption.

---

## 7. Make web search failures loud, not silent

**Status:** Quality-of-life fix. Bites you in subtle ways.

**The problem.** `WebResearcher` falls back to DuckDuckGo when `BRAVE_API_KEY` isn't set. DDGS has aggressive rate limiting and frequently returns nothing or errors out. The agent gets back an empty list or an error string and concludes "no relevant news exists" when really the search just failed.

**What to build.** Two changes:

1. Log search failures at WARN level with the query and the failure reason. You want to see in your logs when the agent thought it had researched something but actually hadn't.
2. Either require Brave (it's cheap, ~$5/mo for hobby use) or surface the degraded state to the agent: "Search is unavailable in this session — do not trade based on assumptions about current news."

**Why it matters.** Silent degradation is the worst kind of bug in an agent system. The agent confidently makes decisions based on missing information and you don't know it happened until you look at trade-by-trade reasoning.

---

## Sequencing recommendation

Do them in this order: 2 → 1 → 4 → 5 → 3 → 6 → 7.

The transaction fix (2) is small and unblocks safe concurrency. The theses table (1) is the foundation for everything analytical. Performance review (4) and prompt tightening (5) are the immediate behavioral wins on top of the new schema. Code execution (3) is a bigger refactor and benefits from being done after the data model has stabilized. The smaller fixes (6, 7) can land any time but are easy to forget if you don't write them down.

The biggest single change is item 1. If you do nothing else from this list, do that one — it's what makes the project produce something durable.