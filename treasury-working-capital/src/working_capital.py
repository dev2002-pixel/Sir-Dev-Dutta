"""Core working-capital metrics calculated from monthly synthetic financial data."""

from __future__ import annotations

from pathlib import Path
import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def calculate_working_capital_metrics(
    receivables: pd.DataFrame, payables: pd.DataFrame, inventory: pd.DataFrame,
    income_statement: pd.DataFrame,
) -> pd.DataFrame:
    """Return DSO, DIO, DPO, CCC and net working capital by month.

    The convention is a 365-day annualisation. Input data must have a `month`
    field and ending balances; sales and COGS are annualised from monthly values.
    """
    frames = [receivables, payables, inventory, income_statement]
    merged = frames[0]
    for frame in frames[1:]:
        merged = merged.merge(frame, on="month", validate="one_to_one")

    required = {"month", "accounts_receivable", "accounts_payable", "inventory", "sales", "cogs"}
    missing = required - set(merged.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    result = merged.copy()
    result["dso"] = result["accounts_receivable"] / (result["sales"] * 12) * 365
    result["dio"] = result["inventory"] / (result["cogs"] * 12) * 365
    result["dpo"] = result["accounts_payable"] / (result["cogs"] * 12) * 365
    result["cash_conversion_cycle"] = result["dso"] + result["dio"] - result["dpo"]
    result["net_working_capital"] = result["accounts_receivable"] + result["inventory"] - result["accounts_payable"]
    # Include balance sheet columns alongside metrics
    return result[["month", "accounts_receivable", "inventory", "accounts_payable", "dso", "dio", "dpo", "cash_conversion_cycle", "net_working_capital"]].round(2)


def load_default_data(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load the bundled synthetic data and calculate metrics."""
    return calculate_working_capital_metrics(
        pd.read_csv(data_dir / "receivables.csv"),
        pd.read_csv(data_dir / "payables.csv"),
        pd.read_csv(data_dir / "inventory.csv"),
        pd.read_csv(data_dir / "income_statement.csv"),
    )


if __name__ == "__main__":
    print(load_default_data().to_string(index=False))
