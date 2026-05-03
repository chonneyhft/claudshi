import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.models import PerformanceSnapshot, Position, Thesis, Trade


class Database:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.row_factory = sqlite3.Row
        self._in_transaction = False
        self._init_schema()

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        self._in_transaction = True
        try:
            yield
            self.conn.execute("COMMIT")
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        finally:
            self._in_transaction = False

    def _commit(self):
        if not self._in_transaction:
            self.conn.commit()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                market_title TEXT,
                side TEXT NOT NULL,
                action TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price_cents INTEGER NOT NULL,
                total_cost_cents INTEGER NOT NULL,
                reasoning TEXT,
                session_id TEXT,
                timestamp TEXT NOT NULL,
                thesis_id TEXT
            );

            CREATE TABLE IF NOT EXISTS theses (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                side_predicted TEXT NOT NULL,
                category TEXT,
                entry_thesis TEXT NOT NULL,
                probability_estimate INTEGER NOT NULL,
                market_price_at_entry INTEGER NOT NULL,
                edge_cents INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                exit_thesis TEXT,
                outcome TEXT,
                realized_pnl_cents INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                closed_at TEXT,
                session_id TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT PRIMARY KEY,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                avg_price_cents INTEGER NOT NULL,
                opened_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS portfolio_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                balance_cents INTEGER NOT NULL,
                realized_pnl_cents INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                balance_cents INTEGER NOT NULL,
                positions_value_cents INTEGER NOT NULL,
                total_value_cents INTEGER NOT NULL,
                realized_pnl_cents INTEGER NOT NULL,
                unrealized_pnl_cents INTEGER NOT NULL,
                num_positions INTEGER NOT NULL
            );
        """)
        self._commit()
        self._migrate()

    def _migrate(self):
        cursor = self.conn.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cursor.fetchall()]
        if "thesis_id" not in columns:
            self.conn.execute("ALTER TABLE trades ADD COLUMN thesis_id TEXT")
            self._commit()

    def seed_portfolio(self, starting_balance_cents: int):
        row = self.conn.execute("SELECT id FROM portfolio_state WHERE id = 1").fetchone()
        if not row:
            self.conn.execute(
                "INSERT INTO portfolio_state (id, balance_cents, realized_pnl_cents) VALUES (1, ?, 0)",
                (starting_balance_cents,),
            )
            self._commit()

    def get_portfolio_state(self) -> tuple[int, int]:
        row = self.conn.execute("SELECT balance_cents, realized_pnl_cents FROM portfolio_state WHERE id = 1").fetchone()
        if not row:
            return 0, 0
        return row["balance_cents"], row["realized_pnl_cents"]

    def update_balance(self, new_balance: int):
        self.conn.execute("UPDATE portfolio_state SET balance_cents = ? WHERE id = 1", (new_balance,))
        self._commit()

    def add_realized_pnl(self, pnl_cents: int):
        self.conn.execute(
            "UPDATE portfolio_state SET realized_pnl_cents = realized_pnl_cents + ? WHERE id = 1",
            (pnl_cents,),
        )
        self._commit()

    def save_trade(self, trade: Trade):
        self.conn.execute(
            """INSERT INTO trades (id, ticker, market_title, side, action, quantity,
               price_cents, total_cost_cents, reasoning, session_id, timestamp, thesis_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.id, trade.ticker, trade.market_title, trade.side,
                trade.action, trade.quantity, trade.price_cents,
                trade.total_cost_cents, trade.reasoning, trade.session_id,
                trade.timestamp.isoformat(), trade.thesis_id or None,
            ),
        )
        self._commit()

    # --- Thesis methods ---

    def save_thesis(self, thesis: Thesis):
        self.conn.execute(
            """INSERT INTO theses (id, ticker, side_predicted, category, entry_thesis,
               probability_estimate, market_price_at_entry, edge_cents, status,
               exit_thesis, outcome, realized_pnl_cents, created_at, closed_at, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                thesis.id, thesis.ticker, thesis.side_predicted, thesis.category,
                thesis.entry_thesis, thesis.probability_estimate,
                thesis.market_price_at_entry, thesis.edge_cents, thesis.status,
                thesis.exit_thesis, thesis.outcome, thesis.realized_pnl_cents,
                thesis.created_at.isoformat(),
                thesis.closed_at.isoformat() if thesis.closed_at else None,
                thesis.session_id,
            ),
        )
        self._commit()

    def update_thesis(self, thesis_id: str, **kwargs):
        allowed = {
            "entry_thesis", "exit_thesis", "status", "outcome",
            "realized_pnl_cents", "closed_at", "probability_estimate", "category",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values())
        values.append(thesis_id)
        self.conn.execute(
            f"UPDATE theses SET {set_clause} WHERE id = ?", values
        )
        self._commit()

    def get_thesis(self, thesis_id: str) -> Optional[Thesis]:
        row = self.conn.execute("SELECT * FROM theses WHERE id = ?", (thesis_id,)).fetchone()
        if not row:
            return None
        return self._row_to_thesis(row)

    def get_theses(self, status: Optional[str] = None, limit: int = 50) -> list[Thesis]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM theses WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM theses ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_thesis(r) for r in rows]

    def get_theses_for_ticker(self, ticker: str) -> list[Thesis]:
        rows = self.conn.execute(
            "SELECT * FROM theses WHERE ticker = ? AND status = 'active' ORDER BY created_at DESC",
            (ticker,),
        ).fetchall()
        return [self._row_to_thesis(r) for r in rows]

    def _row_to_thesis(self, row) -> Thesis:
        return Thesis(
            id=row["id"],
            ticker=row["ticker"],
            side_predicted=row["side_predicted"],
            category=row["category"] or "",
            entry_thesis=row["entry_thesis"],
            probability_estimate=row["probability_estimate"],
            market_price_at_entry=row["market_price_at_entry"],
            edge_cents=row["edge_cents"] or 0,
            status=row["status"],
            exit_thesis=row["exit_thesis"] or "",
            outcome=row["outcome"] or "",
            realized_pnl_cents=row["realized_pnl_cents"] or 0,
            created_at=datetime.fromisoformat(row["created_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            session_id=row["session_id"],
        )

    def upsert_position(self, position: Position):
        self.conn.execute(
            """INSERT INTO positions (ticker, side, quantity, avg_price_cents, opened_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(ticker) DO UPDATE SET
               side = excluded.side,
               quantity = excluded.quantity,
               avg_price_cents = excluded.avg_price_cents""",
            (
                position.ticker, position.side, position.quantity,
                position.avg_price_cents, position.opened_at.isoformat(),
            ),
        )
        self._commit()

    def delete_position(self, ticker: str):
        self.conn.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
        self._commit()

    def get_positions(self) -> list[Position]:
        rows = self.conn.execute("SELECT * FROM positions").fetchall()
        return [
            Position(
                ticker=r["ticker"],
                side=r["side"],
                quantity=r["quantity"],
                avg_price_cents=r["avg_price_cents"],
                opened_at=datetime.fromisoformat(r["opened_at"]),
            )
            for r in rows
        ]

    def get_trades(self, limit: int = 100) -> list[Trade]:
        rows = self.conn.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            Trade(
                id=r["id"],
                ticker=r["ticker"],
                market_title=r["market_title"] or "",
                side=r["side"],
                action=r["action"],
                quantity=r["quantity"],
                price_cents=r["price_cents"],
                total_cost_cents=r["total_cost_cents"],
                reasoning=r["reasoning"] or "",
                session_id=r["session_id"] or "",
                thesis_id=r["thesis_id"] or "",
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rows
        ]

    def get_trade_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM trades").fetchone()
        return row["cnt"]

    def save_snapshot(self, snapshot: PerformanceSnapshot):
        self.conn.execute(
            """INSERT INTO portfolio_snapshots
               (timestamp, balance_cents, positions_value_cents, total_value_cents,
                realized_pnl_cents, unrealized_pnl_cents, num_positions)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.timestamp.isoformat(),
                snapshot.balance_cents,
                snapshot.positions_value_cents,
                snapshot.total_value_cents,
                snapshot.realized_pnl_cents,
                snapshot.unrealized_pnl_cents,
                snapshot.num_positions,
            ),
        )
        self._commit()

    def get_snapshots(self) -> list[PerformanceSnapshot]:
        rows = self.conn.execute(
            "SELECT * FROM portfolio_snapshots ORDER BY timestamp ASC"
        ).fetchall()
        return [
            PerformanceSnapshot(
                timestamp=datetime.fromisoformat(r["timestamp"]),
                balance_cents=r["balance_cents"],
                positions_value_cents=r["positions_value_cents"],
                total_value_cents=r["total_value_cents"],
                realized_pnl_cents=r["realized_pnl_cents"],
                unrealized_pnl_cents=r["unrealized_pnl_cents"],
                num_positions=r["num_positions"],
            )
            for r in rows
        ]
