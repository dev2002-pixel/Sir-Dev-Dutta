import pandas as pd
from .econometrics import generate_positions

def run_backtest(frame: pd.DataFrame, entry: float = 2.0, exit: float = 0.5, cost_bps: float = 5.0) -> pd.DataFrame:
    """Daily close-to-close spread backtest with one-bar lagged positions."""
    out = frame.copy()
    out["target_position"] = generate_positions(out["zscore"], entry, exit)
    out["position"] = out["target_position"].shift(1).fillna(0.0)
    ret_a = out["asset_a"].pct_change().fillna(0.0)
    ret_b = out["asset_b"].pct_change().fillna(0.0)
    beta = float(out.attrs.get("beta", 1.0))
    spread_return = (ret_a - beta * ret_b) / (1.0 + abs(beta))
    out["gross_return"] = out["position"] * spread_return
    out["turnover"] = out["position"].diff().abs().fillna(out["position"].abs())
    out["transaction_cost"] = out["turnover"] * (cost_bps / 10_000.0)
    out["net_return"] = out["gross_return"] - out["transaction_cost"]
    out["equity"] = (1.0 + out["net_return"]).cumprod()
    return out
