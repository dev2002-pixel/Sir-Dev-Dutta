import pytest
from india_quant.execution import OrderBookSnapshot, simulate_market_order

def test_buy_fills_above_mid():
    book = OrderBookSnapshot(99.95, 100.05, 500, 500)
    result = simulate_market_order(book, "buy", 100)
    assert result["estimated_fill_price"] > result["mid_price"]

def test_invalid_side_rejected():
    book = OrderBookSnapshot(99.95, 100.05, 500, 500)
    with pytest.raises(ValueError):
        simulate_market_order(book, "hold", 100)
