import numpy as np
import pandas as pd

def performance_metrics(returns: pd.Series, positions: pd.Series) -> dict:
    r = returns.dropna().astype(float)
    if r.empty:
        return {}
    equity = (1.0 + r).cumprod()
    years = len(r) / 252.0
    total_return = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else float("nan")
    vol = float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else float("nan")
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 and r.std(ddof=1) > 0 else float("nan")
    drawdown = equity / equity.cummax() - 1.0
    return {"observations": int(len(r)), "total_return": total_return, "cagr": cagr,
            "annualized_volatility": vol, "sharpe_ratio": sharpe,
            "max_drawdown": float(drawdown.min()),
            "turnover": float(positions.diff().abs().fillna(positions.abs()).sum()),
            "position_changes": int(positions.diff().fillna(positions).ne(0).sum())}
