import numpy as np
import pandas as pd

def estimate_hedge_ratio(train: pd.DataFrame) -> tuple[float, float]:
    """OLS: log(asset_a) = alpha + beta * log(asset_b) + error."""
    y = np.log(train["asset_a"].to_numpy(dtype=float))
    x = np.log(train["asset_b"].to_numpy(dtype=float))
    design = np.column_stack([np.ones(len(x)), x])
    alpha, beta = np.linalg.lstsq(design, y, rcond=None)[0]
    return float(alpha), float(beta)

def cointegration_diagnostic(train: pd.DataFrame) -> dict:
    """Engle-Granger diagnostic; a test result is not a profitability claim."""
    try:
        from statsmodels.tsa.stattools import coint
        statistic, pvalue, critical = coint(np.log(train["asset_a"]), np.log(train["asset_b"]))
        return {"test": "Engle-Granger", "statistic": float(statistic),
                "p_value": float(pvalue), "critical_values": [float(v) for v in critical]}
    except ImportError:
        return {"test": "Engle-Granger", "status": "statsmodels unavailable"}

def make_spread_and_zscore(prices: pd.DataFrame, alpha: float, beta: float, window: int = 60) -> pd.DataFrame:
    """Calculate residual spread and trailing z-score without future observations."""
    out = prices.copy()
    out["spread"] = np.log(out["asset_a"]) - alpha - beta * np.log(out["asset_b"])
    mean = out["spread"].rolling(window, min_periods=window).mean()
    std = out["spread"].rolling(window, min_periods=window).std(ddof=1)
    out["zscore"] = (out["spread"] - mean) / std.replace(0, np.nan)
    return out

def generate_positions(zscore: pd.Series, entry: float = 2.0, exit: float = 0.5) -> pd.Series:
    """Stateful mean-reversion positions: +1 long spread, -1 short spread."""
    if entry <= exit or exit < 0:
        raise ValueError("Require entry > exit >= 0.")
    position, values = 0, []
    for z in zscore:
        if not np.isfinite(z):
            position = 0
        elif position == 0:
            if z <= -entry:
                position = 1
            elif z >= entry:
                position = -1
        elif abs(z) <= exit:
            position = 0
        values.append(position)
    return pd.Series(values, index=zscore.index, dtype=float)
