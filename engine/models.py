from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Position(BaseModel):
    ticker: str
    side: Literal["yes", "no"]
    quantity: int
    avg_price_cents: int
    current_price_cents: int = 0
    opened_at: datetime = Field(default_factory=datetime.now)

    @property
    def cost_basis_cents(self) -> int:
        return self.avg_price_cents * self.quantity

    @property
    def market_value_cents(self) -> int:
        return self.current_price_cents * self.quantity

    @property
    def unrealized_pnl_cents(self) -> int:
        return self.market_value_cents - self.cost_basis_cents


class Trade(BaseModel):
    id: str
    ticker: str
    market_title: str
    side: Literal["yes", "no"]
    action: Literal["buy", "sell"]
    quantity: int
    price_cents: int
    total_cost_cents: int
    timestamp: datetime = Field(default_factory=datetime.now)
    reasoning: str = ""
    session_id: str = ""
    thesis_id: str = ""


class Thesis(BaseModel):
    id: str
    ticker: str
    side_predicted: Literal["yes", "no"]
    category: str = ""
    entry_thesis: str
    probability_estimate: int
    market_price_at_entry: int
    edge_cents: int = 0
    status: Literal["active", "closed", "settled"] = "active"
    exit_thesis: str = ""
    outcome: Literal["win", "loss", "partial", ""] = ""
    realized_pnl_cents: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    session_id: str = ""


class Portfolio(BaseModel):
    balance_cents: int
    positions: list[Position] = []
    total_trades: int = 0
    realized_pnl_cents: int = 0

    @property
    def positions_value_cents(self) -> int:
        return sum(p.market_value_cents for p in self.positions)

    @property
    def total_value_cents(self) -> int:
        return self.balance_cents + self.positions_value_cents

    @property
    def unrealized_pnl_cents(self) -> int:
        return sum(p.unrealized_pnl_cents for p in self.positions)

    @property
    def total_pnl_cents(self) -> int:
        return self.realized_pnl_cents + self.unrealized_pnl_cents


class PerformanceSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    balance_cents: int = 0
    positions_value_cents: int = 0
    total_value_cents: int = 0
    realized_pnl_cents: int = 0
    unrealized_pnl_cents: int = 0
    num_positions: int = 0
