"""GitHub-friendly Monte Carlo liquidity visualizations."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd


def _paths(forecast: pd.DataFrame, simulations: int, seed: int, volatility: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base_net = forecast["net_cash_flow"].to_numpy(dtype=float)
    opening = float(forecast["opening_cash"].iloc[0])
    shocks = rng.normal(0, volatility, size=(simulations, len(base_net)))
    return opening + (base_net * (1 + shocks)).cumsum(axis=1)


def create_monte_carlo_paths_chart(forecast, threshold, output_path: Path, simulations=10_000, seed=42, volatility=0.12, paths_to_plot=100):
    paths = _paths(forecast, simulations, seed, volatility)
    p05, p50, p95 = np.quantile(paths, [0.05, 0.50, 0.95], axis=0)
    x = np.arange(1, paths.shape[1] + 1)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for path in paths[:min(paths_to_plot, simulations)]:
        ax.plot(x, path, alpha=0.08, linewidth=0.8)
    ax.plot(x, p05, linestyle="--", linewidth=2, label="P05")
    ax.plot(x, p50, linewidth=2.5, label="Median")
    ax.plot(x, p95, linestyle="--", linewidth=2, label="P95")
    ax.axhline(threshold, linestyle=":", linewidth=2, label=f"Threshold ${threshold:,.0f}")
    ax.set_title("Monte Carlo Liquidity Simulation Paths")
    ax.set_xlabel("Forecast period")
    ax.set_ylabel("Cash balance ($)")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def create_minimum_cash_distribution_chart(forecast, threshold, output_path: Path, simulations=10_000, seed=42, volatility=0.12):
    paths = _paths(forecast, simulations, seed, volatility)
    minimums = paths.min(axis=1)
    breach = float((minimums < threshold).mean())
    p05 = float(np.quantile(minimums, 0.05))
    median = float(np.median(minimums))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.hist(minimums, bins=50, alpha=0.75)
    ax.axvline(threshold, linestyle="--", linewidth=2, label=f"Threshold ${threshold:,.0f}")
    ax.axvline(p05, linestyle=":", linewidth=2, label=f"P05 ${p05:,.0f}")
    ax.set_title("Monte Carlo Distribution of Minimum Cash")
    ax.set_xlabel("Minimum cash ($)")
    ax.set_ylabel("Simulation count")
    ax.text(0.98, 0.95, f"Breach probability: {breach:.2%}\nMedian minimum: ${median:,.0f}", transform=ax.transAxes, ha="right", va="top")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def create_liquidity_fan_chart(forecast, threshold, output_path: Path, simulations=10_000, seed=42, volatility=0.12):
    paths = _paths(forecast, simulations, seed, volatility)
    p05, p25, p50, p75, p95 = np.quantile(paths, [0.05, 0.25, 0.50, 0.75, 0.95], axis=0)
    x = np.arange(1, paths.shape[1] + 1)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.fill_between(x, p05, p95, alpha=0.15, label="P05–P95")
    ax.fill_between(x, p25, p75, alpha=0.25, label="P25–P75")
    ax.plot(x, p50, linewidth=2.5, label="Median")
    ax.axhline(threshold, linestyle="--", linewidth=2, label=f"Threshold ${threshold:,.0f}")
    ax.set_title("Liquidity Forecast — Monte Carlo Percentile Bands")
    ax.set_xlabel("Forecast period")
    ax.set_ylabel("Cash balance ($)")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path
