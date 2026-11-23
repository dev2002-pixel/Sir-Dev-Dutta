"""Generate deterministic synthetic prices for a runnable example."""
from pathlib import Path
import numpy as np
import pandas as pd

def main():
    rng = np.random.default_rng(17)
    n = 1500
    dates = pd.bdate_range("2019-01-01", periods=n)
    common = np.cumsum(rng.normal(0.00025, 0.009, n))
    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = 0.88 * spread[t - 1] + rng.normal(0, 0.006)
    log_b = np.log(100.0) + common
    log_a = np.log(80.0) + 0.85 * common + spread
    df = pd.DataFrame({"date": dates, "asset_a": np.exp(log_a), "asset_b": np.exp(log_b)})
    out = Path(__file__).parent / "data" / "sample_prices.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} synthetic observations to {out}")

if __name__ == "__main__":
    main()
