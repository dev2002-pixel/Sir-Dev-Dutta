"""SOFR forecasting and treasury sensitivity analysis using synthetic data.

The project deliberately uses synthetic SOFR observations so no market-data
license or real company data is required. The forecast is a transparent
AR(1)-style model estimated with ordinary least squares.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_synthetic_sofr(periods: int = 12) -> pd.DataFrame:
    """Create reproducible monthly SOFR observations in percent."""
    dates = pd.date_range("2025-01-01", periods=periods, freq="MS")
    rates = np.array([4.33, 4.34, 4.32, 4.35, 4.37, 4.36, 4.34, 4.31, 4.28, 4.25, 4.22, 4.20])
    return pd.DataFrame({"month": dates, "sofr_pct": rates[:periods]})


def forecast_sofr(history: pd.DataFrame, horizon: int = 6) -> pd.DataFrame:
    """Forecast SOFR with an AR(1) regression: r_t = a + b*r_(t-1) + e_t."""
    if not {"month", "sofr_pct"}.issubset(history.columns):
        raise ValueError("SOFR history requires month and sofr_pct columns")
    y = history["sofr_pct"].astype(float).to_numpy()
    if len(y) < 4:
        raise ValueError("At least four SOFR observations are required")
    x = y[:-1]
    target = y[1:]
    X = np.column_stack([np.ones(len(x)), x])
    alpha, beta = np.linalg.lstsq(X, target, rcond=None)[0]
    residuals = target - (alpha + beta * x)
    sigma = float(np.std(residuals, ddof=2)) if len(residuals) > 2 else 0.01

    last = float(y[-1])
    future_dates = pd.date_range(pd.to_datetime(history["month"].iloc[-1]) + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    forecasts = []
    for _ in range(horizon):
        last = alpha + beta * last
        forecasts.append(last)
    result = pd.DataFrame({"month": future_dates, "sofr_pct": forecasts})
    result["lower_95"] = result["sofr_pct"] - 1.96 * sigma
    result["upper_95"] = result["sofr_pct"] + 1.96 * sigma
    result["model_alpha"] = alpha
    result["model_beta"] = beta
    return result


def analyze_sofr_relationships(sofr: pd.DataFrame, metrics: pd.DataFrame, forecast: pd.DataFrame) -> pd.DataFrame:
    """Merge SOFR with working-capital metrics and estimate correlations."""
    merged = metrics.copy()
    merged["month"] = pd.to_datetime(merged["month"]).dt.to_period("M").dt.to_timestamp()
    s = sofr.copy()
    s["month"] = pd.to_datetime(s["month"]).dt.to_period("M").dt.to_timestamp()
    joined = merged.merge(s[["month", "sofr_pct"]], on="month", how="inner")
    columns = ["sofr_pct", "dso", "dio", "dpo", "cash_conversion_cycle", "net_working_capital"]
    rows = []
    for col in columns[1:]:
        rows.append({"relationship": f"SOFR vs {col}", "correlation": joined["sofr_pct"].corr(joined[col]), "observations": len(joined)})
    return pd.DataFrame(rows).round(4)


def sensitivity_table(forecast: pd.DataFrame, base_cash: float = 1_500_000) -> pd.DataFrame:
    """Translate SOFR changes into illustrative annual interest expense sensitivity."""
    balances = {"$5m": 5_000_000, "$10m": 10_000_000, "$25m": 25_000_000}
    rows = []
    base_rate = float(forecast["sofr_pct"].iloc[0])
    for label, balance in balances.items():
        for shock in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            rate = base_rate + shock
            annual_interest = balance * rate / 100
            rows.append({"floating_balance": label, "sofr_shock_bps": shock * 100, "sofr_pct": rate, "annual_interest": annual_interest})
    return pd.DataFrame(rows).round(2)
