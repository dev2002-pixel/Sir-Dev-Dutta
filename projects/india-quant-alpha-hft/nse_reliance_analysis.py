"""NSE / Reliance market-linkage research.

Downloads daily adjusted prices with yfinance (Yahoo Finance symbols), then
estimates correlations, HAC regressions, lead-lag relationships and the
mechanical NIFTY contribution implied by an externally supplied index weight.

This is research tooling, not exchange-grade data. Verify all data against
licensed NSE/vendor records before making investment claims.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import statsmodels.api as sm


TICKERS = {
    "RELIANCE": "RELIANCE.NS",
    "NIFTY50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    # Yahoo Finance symbol for Nifty Energy; verify availability/data coverage.
    "NIFTYENERGY": "^CNXENERGY",
}


def download_prices(start: str, end: str, tickers: dict[str, str] = TICKERS) -> pd.DataFrame:
    frames = []
    for label, ticker in tickers.items():
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True,
                          progress=False, threads=False)
        if raw.empty:
            print(f"WARNING: no data returned for {label} ({ticker}); skipping")
            continue
        close = raw["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        frames.append(close.rename(label))
    if not frames:
        raise RuntimeError("No price series downloaded. Check tickers, dates and connectivity.")
    return pd.concat(frames, axis=1).sort_index().dropna(how="all")


def prepare_returns(prices: pd.DataFrame) -> pd.DataFrame:
    prices = prices.copy()
    prices.index = pd.to_datetime(prices.index)
    return np.log(prices.where(prices > 0)).diff().dropna(how="all")


def hac_regression(y: pd.Series, x: pd.Series, maxlags: int = 5) -> dict:
    data = pd.concat([y.rename("y"), x.rename("x")], axis=1).dropna()
    if len(data) < 30:
        return {"n": len(data), "beta": np.nan, "t_stat_hac": np.nan, "r_squared": np.nan}
    fit = sm.OLS(data["y"], sm.add_constant(data["x"])).fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags}
    )
    return {
        "n": int(fit.nobs),
        "alpha": float(fit.params["const"]),
        "beta": float(fit.params["x"]),
        "t_stat_hac": float(fit.tvalues["x"]),
        "p_value_hac": float(fit.pvalues["x"]),
        "r_squared": float(fit.rsquared),
    }


def load_weight(path: str | None, default_weight: float | None) -> pd.Series | None:
    """CSV columns: date, reliance_weight_pct. Weight must be official for each date."""
    if path:
        w = pd.read_csv(path, parse_dates=["date"]).set_index("date")["reliance_weight_pct"]
        w = pd.to_numeric(w, errors="coerce").dropna() / 100.0
        if ((w <= 0) | (w >= 1)).any():
            raise ValueError("reliance_weight_pct must be between 0 and 100")
        return w.sort_index()
    if default_weight is not None:
        if not 0 < default_weight < 100:
            raise ValueError("--weight-pct must be between 0 and 100")
        return pd.Series([default_weight / 100.0], index=[pd.Timestamp("1900-01-01")])
    return None


def event_study(returns: pd.DataFrame, events_path: str) -> pd.DataFrame:
    """Events CSV columns: date,event; computes [-1,+1] and [0,+2] cumulative log returns."""
    events = pd.read_csv(events_path, parse_dates=["date"])
    rows = []
    for _, event in events.iterrows():
        date = pd.Timestamp(event["date"])
        idx = returns.index.get_indexer([date], method="nearest")[0]
        row = {"event_date": date.date().isoformat(), "event": event.get("event", "")}
        for col in returns.columns:
            row[f"{col}_cum_m1_p1"] = returns[col].iloc[max(0, idx-1):idx+2].sum()
            row[f"{col}_cum_0_p2"] = returns[col].iloc[idx:min(len(returns), idx+3)].sum()
        rows.append(row)
    return pd.DataFrame(rows)


def run(prices: pd.DataFrame, output_dir: str, weights: pd.Series | None = None,
        events_path: str | None = None) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    returns = prepare_returns(prices)
    returns.to_csv(out / "daily_log_returns.csv")

    pairs = [c for c in ["NIFTY50", "BANKNIFTY", "NIFTYENERGY"] if c in returns]
    corr = returns[["RELIANCE"] + pairs].corr() if "RELIANCE" in returns else pd.DataFrame()
    corr.to_csv(out / "correlation_matrix.csv")

    rows = []
    if "RELIANCE" in returns:
        for market in pairs:
            rows.append({"market": market, **hac_regression(returns[market], returns["RELIANCE"])})
            # Positive lag k asks whether Reliance return at t-k helps explain market return at t.
            for lag in [1, 2, 3, 5]:
                rows.append({"market": market, "lag_days": lag,
                             **hac_regression(returns[market], returns["RELIANCE"].shift(lag))})
    pd.DataFrame(rows).to_csv(out / "reliance_market_regressions.csv", index=False)

    if weights is not None and "NIFTY50" in returns and "RELIANCE" in returns:
        w = weights.reindex(returns.index, method="ffill")
        contribution = w * returns["RELIANCE"]
        # First-order arithmetic/log-return approximation; clearly label as estimate.
        ex_ril = (returns["NIFTY50"] - contribution) / (1.0 - w)
        pd.DataFrame({
            "reliance_weight": w,
            "reliance_log_return": returns["RELIANCE"],
            "estimated_reliance_nifty_contribution": contribution,
            "nifty50_log_return": returns["NIFTY50"],
            "estimated_nifty_ex_reliance_return": ex_ril,
        }).to_csv(out / "nifty_reliance_contribution.csv")

    if events_path:
        event_study(returns, events_path).to_csv(out / "reliance_event_study.csv", index=False)

    print(f"Saved analysis outputs to: {out.resolve()}")
    print("\nReliance correlations:")
    if not corr.empty:
        print(corr["RELIANCE"].sort_values(ascending=False).to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None, help="Exclusive end date; defaults to latest available")
    parser.add_argument("--prices", default=None, help="Optional local prices CSV with date column")
    parser.add_argument("--weights", default=None, help="Official monthly weights CSV")
    parser.add_argument("--weight-pct", type=float, default=None,
                        help="Optional constant weight for a sensitivity run, not historical truth")
    parser.add_argument("--events", default=None, help="Optional manually curated event CSV")
    parser.add_argument("--output", default="outputs/reliance_nse")
    args = parser.parse_args()

    if args.prices:
        prices = pd.read_csv(args.prices, parse_dates=["date"]).set_index("date")
    else:
        prices = download_prices(args.start, args.end)
    weights = load_weight(args.weights, args.weight_pct)
    run(prices, args.output, weights, args.events)


if __name__ == "__main__":
    main()
