"""Illustrative borrower credit review from a bank's repayment-capacity perspective."""

from __future__ import annotations

from pathlib import Path
import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _status(actual: float, threshold: float, higher_is_better: bool) -> str:
    return "Pass" if (actual >= threshold if higher_is_better else actual <= threshold) else "Breach"


def evaluate_credit_risk(
    credit_inputs: pd.DataFrame, forecast: pd.DataFrame, scenarios: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return covenant/credit tests and an indicative risk summary.

    This is a transparent screening tool, not a calibrated probability-of-default
    model, lending decision, credit rating, or substitute for bank underwriting.
    """
    required = {
        "as_of_date", "gross_debt", "cash_on_hand", "undrawn_facility", "ttm_ebitda",
        "ttm_interest_expense", "ttm_debt_service", "debt_maturity_date",
        "covenant_net_leverage_max", "covenant_interest_coverage_min", "covenant_dscr_min",
        "minimum_cash_threshold",
    }
    if missing := required - set(credit_inputs.columns):
        raise ValueError(f"Missing required credit input columns: {sorted(missing)}")
    if len(credit_inputs) != 1:
        raise ValueError("credit_inputs must contain exactly one borrower snapshot")
    values = credit_inputs.iloc[0]
    if min(values["ttm_ebitda"], values["ttm_interest_expense"], values["ttm_debt_service"]) <= 0:
        raise ValueError("EBITDA, interest expense, and debt service must be positive")

    net_debt = values["gross_debt"] - values["cash_on_hand"]
    net_leverage = net_debt / values["ttm_ebitda"]
    interest_coverage = values["ttm_ebitda"] / values["ttm_interest_expense"]
    dscr = values["ttm_ebitda"] / values["ttm_debt_service"]
    base_min_cash = float(forecast["closing_cash"].min())
    worst_case_cash = float(scenarios["minimum_cash"].min())
    scenario_breach_rate = float(scenarios["threshold_breached"].mean())
    as_of = pd.Timestamp(values["as_of_date"])
    maturity = pd.Timestamp(values["debt_maturity_date"])
    days_to_maturity = int((maturity - as_of).days)
    available_liquidity = base_min_cash + values["undrawn_facility"]

    tests = pd.DataFrame([
        ["Net leverage", net_leverage, values["covenant_net_leverage_max"], "Maximum", _status(net_leverage, values["covenant_net_leverage_max"], False)],
        ["Interest coverage", interest_coverage, values["covenant_interest_coverage_min"], "Minimum", _status(interest_coverage, values["covenant_interest_coverage_min"], True)],
        ["Debt-service coverage", dscr, values["covenant_dscr_min"], "Minimum", _status(dscr, values["covenant_dscr_min"], True)],
        ["Base minimum cash", base_min_cash, values["minimum_cash_threshold"], "Minimum", _status(base_min_cash, values["minimum_cash_threshold"], True)],
    ], columns=["test", "actual", "threshold", "limit_type", "status"])

    covenant_breaches = int((tests["status"] == "Breach").sum())
    # A transparent watchlist score: stress sensitivity, liquidity cushion,
    # near-term refinancing, and covenant breaches. It is deliberately not PD.
    score = scenario_breach_rate * 30
    score += 15 if base_min_cash <= values["minimum_cash_threshold"] else 0
    score += 20 if days_to_maturity <= 365 else (10 if days_to_maturity <= 548 else 0)
    score += covenant_breaches * 15
    score = min(round(score, 1), 100.0)
    tier = "High" if score >= 70 else ("Elevated" if score >= 40 else "Moderate")

    summary = pd.DataFrame([
        ["Indicative risk tier", tier],
        ["Indicative risk score (0-100; not PD)", score],
        ["Net debt", net_debt],
        ["Net leverage (x)", net_leverage],
        ["Interest coverage (x)", interest_coverage],
        ["Debt-service coverage (x)", dscr],
        ["Base minimum cash", base_min_cash],
        ["Available liquidity including undrawn facility", available_liquidity],
        ["Worst stressed cash", worst_case_cash],
        ["Liquidity scenario breach rate", scenario_breach_rate],
        ["Days to debt maturity", days_to_maturity],
        ["Covenant breaches", covenant_breaches],
    ], columns=["metric", "value"])
    return tests.round(2), summary.round(4)


def load_default_credit_inputs(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Load the bundled synthetic credit input snapshot."""
    return pd.read_csv(data_dir / "credit_inputs.csv")
