"""Simple, transparent rolling cash-flow forecast for treasury planning."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def forecast_cash_balance(transactions: pd.DataFrame, opening_cash: float = 1_500_000) -> pd.DataFrame:
    """Aggregate dated cash movements and calculate daily closing cash.

    `amount` is signed: positive for collections/other inflows, negative for
    supplier, payroll, tax, and other outflows.
    """
    required = {"date", "category", "amount"}
    if missing := required - set(transactions.columns):
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    daily = transactions.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["inflows"] = daily["amount"].clip(lower=0)
    daily["outflows"] = -daily["amount"].clip(upper=0)
    daily = daily.groupby("date", as_index=False)[["inflows", "outflows"]].sum().sort_values("date")
    daily["net_cash_flow"] = daily["inflows"] - daily["outflows"]
    daily["opening_cash"] = opening_cash + daily["net_cash_flow"].cumsum().shift(fill_value=0)
    daily["closing_cash"] = daily["opening_cash"] + daily["net_cash_flow"]
    return daily


def load_default_forecast(data_dir: Path = DATA_DIR, opening_cash: float = 1_500_000) -> pd.DataFrame:
    return forecast_cash_balance(pd.read_csv(data_dir / "cash_transactions.csv"), opening_cash)


if __name__ == "__main__":
    print(load_default_forecast().to_string(index=False))
