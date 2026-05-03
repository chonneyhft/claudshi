import uuid
from datetime import datetime, timezone
from typing import List, Optional

import config
from engine.db import Database
from engine.models import PerformanceSnapshot, Portfolio, Position, Trade
from kalshi.client import KalshiDataClient


class PaperTrader:
    def __init__(self, db: Database, kalshi_client: KalshiDataClient):
        self.db = db
        self.kalshi = kalshi_client
        self.db.seed_portfolio(config.STARTING_BALANCE_CENTS)

    def get_portfolio(self) -> Portfolio:
        balance_cents, realized_pnl_cents = self.db.get_portfolio_state()
        positions = self.db.get_positions()

        for pos in positions:
            try:
                market = self.kalshi.get_market(pos.ticker)
                if pos.side == "yes":
                    pos.current_price_cents = market.get("yes_bid") or market.get("last_price") or pos.avg_price_cents
                else:
                    pos.current_price_cents = market.get("no_bid") or pos.avg_price_cents
            except Exception:
                pos.current_price_cents = pos.avg_price_cents

        return Portfolio(
            balance_cents=balance_cents,
            positions=positions,
            total_trades=self.db.get_trade_count(),
            realized_pnl_cents=realized_pnl_cents,
        )

    def place_trade(
        self,
        ticker: str,
        side: str,
        action: str,
        quantity: int,
        reasoning: str,
        session_id: str,
        thesis_id: str = "",
    ) -> Trade:
        market = self.kalshi.get_market(ticker)
        if market.get("status") not in ("open", "active"):
            raise ValueError(f"Market {ticker} is not open (status: {market.get('status')})")

        if action == "buy":
            price_cents = (market.get("yes_ask") if side == "yes" else market.get("no_ask")) or 0
            if price_cents <= 0:
                raise ValueError(f"No ask available for {side} side of {ticker}")
        else:
            price_cents = (market.get("yes_bid") if side == "yes" else market.get("no_bid")) or 0
            if price_cents <= 0:
                raise ValueError(f"No bid available for {side} side of {ticker}")

        total_cost_cents = price_cents * quantity

        with self.db.transaction():
            balance_cents, _ = self.db.get_portfolio_state()

            if action == "buy":
                if total_cost_cents > balance_cents:
                    raise ValueError(
                        f"Insufficient balance: need ${total_cost_cents/100:.2f}, have ${balance_cents/100:.2f}"
                    )

            if action == "sell":
                positions = self.db.get_positions()
                existing = next((p for p in positions if p.ticker == ticker), None)
                if not existing:
                    raise ValueError(f"No position in {ticker} to sell")
                if existing.side != side:
                    raise ValueError(f"Position is {existing.side}, cannot sell {side}")
                if quantity > existing.quantity:
                    raise ValueError(f"Only {existing.quantity} contracts held, cannot sell {quantity}")

            trade = Trade(
                id=str(uuid.uuid4())[:12],
                ticker=ticker,
                market_title=market.get("title", ""),
                side=side,
                action=action,
                quantity=quantity,
                price_cents=price_cents,
                total_cost_cents=total_cost_cents,
                reasoning=reasoning,
                session_id=session_id,
                thesis_id=thesis_id,
                timestamp=datetime.now(timezone.utc),
            )
            self.db.save_trade(trade)

            if action == "buy":
                self.db.update_balance(balance_cents - total_cost_cents)
                self._update_position_buy(ticker, side, quantity, price_cents)
            else:
                self.db.update_balance(balance_cents + total_cost_cents)
                self._update_position_sell(ticker, quantity, price_cents)

        self.take_snapshot()
        return trade

    def _update_position_buy(self, ticker: str, side: str, quantity: int, price_cents: int):
        positions = self.db.get_positions()
        existing = next((p for p in positions if p.ticker == ticker), None)

        if existing:
            new_quantity = existing.quantity + quantity
            new_avg = (
                (existing.avg_price_cents * existing.quantity + price_cents * quantity) // new_quantity
            )
            existing.quantity = new_quantity
            existing.avg_price_cents = new_avg
            self.db.upsert_position(existing)
        else:
            pos = Position(
                ticker=ticker,
                side=side,
                quantity=quantity,
                avg_price_cents=price_cents,
                opened_at=datetime.now(timezone.utc),
            )
            self.db.upsert_position(pos)

    def _update_position_sell(self, ticker: str, quantity: int, sell_price_cents: int):
        positions = self.db.get_positions()
        existing = next((p for p in positions if p.ticker == ticker), None)
        if not existing:
            return

        realized_pnl = (sell_price_cents - existing.avg_price_cents) * quantity
        self.db.add_realized_pnl(realized_pnl)

        if quantity >= existing.quantity:
            self.db.delete_position(ticker)
        else:
            existing.quantity -= quantity
            self.db.upsert_position(existing)

    def settle_positions(self) -> List[Trade]:
        settled = []
        positions = self.db.get_positions()
        for pos in positions:
            trade = self._try_settle(pos)
            if trade:
                settled.append(trade)
        return settled

    def _try_settle(self, pos: Position) -> Optional[Trade]:
        try:
            market = self.kalshi.get_market(pos.ticker)
        except Exception:
            return None

        result = market.get("result")
        if not result:
            return None

        if (result == "yes" and pos.side == "yes") or (result == "no" and pos.side == "no"):
            settle_price = 100
        else:
            settle_price = 0

        proceeds = settle_price * pos.quantity

        with self.db.transaction():
            balance_cents, _ = self.db.get_portfolio_state()
            self.db.update_balance(balance_cents + proceeds)

            realized_pnl = (settle_price - pos.avg_price_cents) * pos.quantity
            self.db.add_realized_pnl(realized_pnl)
            self.db.delete_position(pos.ticker)

            trade = Trade(
                id=str(uuid.uuid4())[:12],
                ticker=pos.ticker,
                market_title=market.get("title", ""),
                side=pos.side,
                action="settle",
                quantity=pos.quantity,
                price_cents=settle_price,
                total_cost_cents=proceeds,
                reasoning=f"Market settled: result={result}",
                session_id="settlement",
                timestamp=datetime.now(timezone.utc),
            )
            self.db.save_trade(trade)

            active_theses = self.db.get_theses_for_ticker(pos.ticker)
            for thesis in active_theses:
                outcome = "win" if settle_price == 100 else "loss"
                self.db.update_thesis(
                    thesis.id,
                    status="settled",
                    outcome=outcome,
                    exit_thesis=f"Market settled: result={result}",
                    realized_pnl_cents=(settle_price - thesis.market_price_at_entry) * pos.quantity,
                    closed_at=datetime.now(timezone.utc).isoformat(),
                )

        self.take_snapshot()
        return trade

    def get_trade_history(self, limit: int = 50) -> List[Trade]:
        return self.db.get_trades(limit)

    def take_snapshot(self):
        portfolio = self.get_portfolio()
        snapshot = PerformanceSnapshot(
            timestamp=datetime.now(timezone.utc),
            balance_cents=portfolio.balance_cents,
            positions_value_cents=portfolio.positions_value_cents,
            total_value_cents=portfolio.total_value_cents,
            realized_pnl_cents=portfolio.realized_pnl_cents,
            unrealized_pnl_cents=portfolio.unrealized_pnl_cents,
            num_positions=len(portfolio.positions),
        )
        self.db.save_snapshot(snapshot)
