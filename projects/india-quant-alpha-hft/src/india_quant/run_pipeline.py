from pathlib import Path
import json
import matplotlib.pyplot as plt
from .data import load_prices
from .econometrics import estimate_hedge_ratio, cointegration_diagnostic, make_spread_and_zscore
from .backtest import run_backtest
from .metrics import performance_metrics
from .execution import OrderBookSnapshot, simulate_market_order

ROOT = Path(__file__).resolve().parents[2]

def main():
    prices = load_prices(ROOT / "data" / "sample_prices.csv")
    split = int(len(prices) * 0.60)
    train, test = prices.iloc[:split].copy(), prices.iloc[split:].copy()
    alpha, beta = estimate_hedge_ratio(train)
    diagnostic = cointegration_diagnostic(train)
    model = make_spread_and_zscore(test, alpha, beta, window=60)
    model.attrs["beta"] = beta
    results = run_backtest(model, entry=2.0, exit=0.5, cost_bps=5.0)
    metrics = performance_metrics(results["net_return"], results["position"])
    demo_book = OrderBookSnapshot(100.00, 100.05, 800, 650)
    execution_example = simulate_market_order(demo_book, "buy", 300)
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    results.to_csv(out / "backtest_results.csv", index=False)
    summary = {"data": "synthetic demonstration data", "train_observations": len(train),
               "test_observations": len(test), "alpha": alpha, "beta": beta,
               "cointegration": diagnostic,
               "parameters": {"entry_z": 2.0, "exit_z": 0.5, "cost_bps": 5.0},
               "performance": metrics, "execution_example": execution_example}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(results["date"], results["zscore"], label="Spread z-score")
    axes[0].axhline(2, linestyle="--"); axes[0].axhline(-2, linestyle="--"); axes[0].axhline(0, linewidth=0.8)
    axes[0].set_title("Out-of-sample spread z-score"); axes[0].legend()
    axes[1].plot(results["date"], results["equity"], label="Net equity curve")
    axes[1].set_title("Out-of-sample equity curve after simplified costs"); axes[1].legend()
    fig.tight_layout(); fig.savefig(out / "equity_curve.png", dpi=160); plt.close(fig)
    print(json.dumps(summary, indent=2))
    print(f"Saved outputs to: {out}")

if __name__ == "__main__":
    main()
