"""Liquidity threshold stress tests and reproducible Monte Carlo analysis."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from cash_forecast import load_default_forecast


def run_liquidity_scenarios(
    base_forecast: pd.DataFrame, threshold: float = 1_000_000,
    collection_shocks: tuple[float, ...] = (0.0, -0.05, -0.10),
    outflow_shocks: tuple[float, ...] = (0.0, 0.05, 0.10),
) -> pd.DataFrame:
    """Stress inflows and outflows independently; report the lowest cash balance."""
    rows = []
    opening_cash = float(base_forecast["opening_cash"].iloc[0])
    if {"inflows", "outflows"} <= set(base_forecast.columns):
        inflows = base_forecast["inflows"].to_numpy()
        outflows = base_forecast["outflows"].to_numpy()
    else:
        net = base_forecast["net_cash_flow"].to_numpy()
        inflows, outflows = np.clip(net, 0, None), np.clip(-net, 0, None)
    for collection_shock in collection_shocks:
        for outflow_shock in outflow_shocks:
            stressed_net = inflows * (1 + collection_shock) - outflows * (1 + outflow_shock)
            closing = opening_cash + stressed_net.cumsum()
            rows.append({
                "collection_shock_pct": collection_shock * 100,
                "outflow_shock_pct": outflow_shock * 100,
                "minimum_cash": closing.min(),
                "threshold_breached": bool((closing < threshold).any()),
            })
    return pd.DataFrame(rows).round(2)


def monte_carlo_liquidity(
    base_forecast: pd.DataFrame, threshold: float = 1_000_000,
    simulations: int = 10_000, seed: int = 42,
    daily_volatility: float = 0.12,
) -> dict[str, float]:
    """Estimate breach likelihood by applying independent normal shocks to daily cash flows."""
    if simulations < 1 or daily_volatility < 0:
        raise ValueError("simulations must be positive and daily_volatility non-negative")
    rng = np.random.default_rng(seed)
    base_net = base_forecast["net_cash_flow"].to_numpy()
    opening_cash = float(base_forecast["opening_cash"].iloc[0])
    shocks = rng.normal(0, daily_volatility, size=(simulations, len(base_net)))
    paths = opening_cash + (base_net * (1 + shocks)).cumsum(axis=1)
    minimums = paths.min(axis=1)
    return {
        "simulations": simulations,
        "liquidity_threshold": threshold,
        "breach_probability": float((minimums < threshold).mean()),
        "p05_minimum_cash": float(np.quantile(minimums, 0.05)),
        "median_minimum_cash": float(np.median(minimums)),
    }


if __name__ == "__main__":
    forecast = load_default_forecast()
    print(run_liquidity_scenarios(forecast).to_string(index=False))
    print(monte_carlo_liquidity(forecast))
