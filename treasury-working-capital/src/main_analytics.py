"""Run all Treasury analytics and save tables and charts for GitHub viewing."""

from __future__ import annotations

from pathlib import Path
from cash_forecast import load_default_forecast
from credit_risk import evaluate_credit_risk, load_default_credit_inputs
from scenario_analysis import monte_carlo_liquidity, run_liquidity_scenarios
from sofr_analysis import analyze_sofr_relationships, forecast_sofr, load_synthetic_sofr, sensitivity_table
from sofr_visualizations import create_sofr_forecast_chart, create_sofr_relationship_chart, create_sofr_sensitivity_chart
from visualizations import (
    create_balance_sheet_chart,
    create_cash_flow_chart,
    create_efficiency_metrics_chart,
    create_liquidity_chart,
    create_working_capital_chart,
)
from working_capital import load_default_data

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "reports"
THRESHOLD = 1_000_000


def run() -> dict[str, Path]:
    """Produce reproducible report tables and figures from synthetic data."""
    metrics = load_default_data()
    forecast = load_default_forecast()
    scenarios = run_liquidity_scenarios(forecast, threshold=THRESHOLD)
    simulation = monte_carlo_liquidity(forecast, threshold=THRESHOLD)
    credit_tests, credit_summary = evaluate_credit_risk(load_default_credit_inputs(), forecast, scenarios)

    # SOFR module: forecast the benchmark rate, quantify relationships with
    # working-capital metrics, and translate rate shocks into interest expense.
    sofr_history = load_synthetic_sofr()
    sofr_prediction = forecast_sofr(sofr_history, horizon=6)
    sofr_relationships = analyze_sofr_relationships(sofr_history, metrics, forecast)
    sofr_sensitivity = sensitivity_table(sofr_prediction)

    tables = REPORTS_DIR / "tables"
    figures = REPORTS_DIR / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(tables / "working_capital_metrics.csv", index=False)
    forecast.to_csv(tables / "cash_forecast.csv", index=False)
    scenarios.to_csv(tables / "liquidity_scenarios.csv", index=False)
    credit_tests.to_csv(tables / "credit_tests.csv", index=False)
    credit_summary.to_csv(tables / "credit_risk_summary.csv", index=False)
    sofr_history.to_csv(tables / "sofr_history.csv", index=False)
    sofr_prediction.to_csv(tables / "sofr_forecast.csv", index=False)
    sofr_relationships.to_csv(tables / "sofr_relationships.csv", index=False)
    sofr_sensitivity.to_csv(tables / "sofr_sensitivity.csv", index=False)
    (tables / "monte_carlo_summary.csv").write_text(
        "metric,value\n" + "\n".join(f"{key},{value}" for key, value in simulation.items()) + "\n"
    )
    return {
        "working_capital_efficiency": create_working_capital_chart(metrics, figures / "working_capital_efficiency.svg"),
        "dso_dio_dpo_trend": create_efficiency_metrics_chart(metrics, figures / "dso_dio_dpo_trend.svg"),
        "balance_sheet_drivers": create_balance_sheet_chart(metrics, figures / "working_capital_drivers.svg"),
        "cash_flow_dynamics": create_cash_flow_chart(forecast, figures / "cash_flow_dynamics.svg"),
        "liquidity_stress_test": create_liquidity_chart(forecast, scenarios, THRESHOLD, figures / "liquidity_stress_test.svg"),
        "sofr_forecast": create_sofr_forecast_chart(sofr_history, sofr_prediction, figures / "sofr_forecast.svg"),
        "sofr_relationships": create_sofr_relationship_chart(sofr_relationships, figures / "sofr_relationships.svg"),
        "sofr_sensitivity": create_sofr_sensitivity_chart(sofr_sensitivity, figures / "sofr_sensitivity.svg"),
    }


if __name__ == "__main__":
    created = run()
    print("Analytics report created:")
    for name, path in created.items():
        print(f"- {name}: {path.relative_to(PROJECT_DIR)}")
