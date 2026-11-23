from dataclasses import dataclass

@dataclass
class OrderBookSnapshot:
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def order_flow_imbalance(self) -> float:
        total = self.bid_size + self.ask_size
        return 0.0 if total <= 0 else (self.bid_size - self.ask_size) / total

def simulate_market_order(book: OrderBookSnapshot, side: str, quantity: float, impact_coefficient: float = 0.0005) -> dict:
    """Simplified touch fill plus size-dependent impact; not a matching-engine model."""
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if book.bid <= 0 or book.ask < book.bid:
        raise ValueError("Invalid bid/ask")
    if book.bid_size < 0 or book.ask_size < 0:
        raise ValueError("Displayed sizes cannot be negative")
    touch = book.ask if side == "buy" else book.bid
    depth = max(book.ask_size if side == "buy" else book.bid_size, 1.0)
    impact = impact_coefficient * (quantity / depth) * book.mid
    fill = touch + impact if side == "buy" else touch - impact
    return {"side": side, "quantity": float(quantity), "mid_price": float(book.mid),
            "touch_price": float(touch), "estimated_impact": float(impact),
            "estimated_fill_price": float(fill), "spread_bps": float(book.spread / book.mid * 10000),
            "ofi": float(book.order_flow_imbalance)}
