from pathlib import Path
import pandas as pd

REQUIRED_COLUMNS = {"date", "asset_a", "asset_b"}

def load_prices(path: str | Path) -> pd.DataFrame:
    """Load and validate two positive price series."""
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    df = df.loc[:, ["date", "asset_a", "asset_b"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="raise")
    for col in ("asset_a", "asset_b"):
        df[col] = pd.to_numeric(df[col], errors="raise")
    df = df.sort_values("date").reset_index(drop=True)
    if df["date"].duplicated().any():
        raise ValueError("Duplicate dates/timestamps are not allowed.")
    if df[["asset_a", "asset_b"]].isna().any().any():
        raise ValueError("Price data contains missing values.")
    if (df[["asset_a", "asset_b"]] <= 0).any().any():
        raise ValueError("Prices must be strictly positive.")
    if len(df) < 100:
        raise ValueError("At least 100 observations are required.")
    return df
