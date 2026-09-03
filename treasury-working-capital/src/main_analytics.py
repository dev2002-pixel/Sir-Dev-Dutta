"""Run all Treasury analytics and save tables and charts for GitHub viewing."""

from __future__ import annotations

from pathlib import Path
from cash_forecast import load_default_forecast
from scenario_analysis import monte_carlo_liquidity, run_liquidity_scenarios
from visualizations import create_liquidity_chart, create_working_capital_chart
from working_capital import load_default_data

PROJECT_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_DIR / "reports"
THRESHOLD = 1_000_000


def run() -> dict[str, Path]:
    """Produce reproducible report tables and figures from the bundled synthetic data."""
    metrics = load_default_data()
    forecast = load_default_forecast()
    scenarios = run_liquidity_scenarios(forecast, threshold=THRESHOLD)
    simulation = monte_carlo_liquidity(forecast, threshold=THRESHOLD)
    tables = REPORTS_DIR / "tables"
    figures = REPORTS_DIR / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(tables / "working_capital_metrics.csv", index=False)
    forecast.to_csv(tables / "cash_forecast.csv", index=False)
    scenarios.to_csv(tables / "liquidity_scenarios.csv", index=False)
    (tables / "monte_carlo_summary.csv").write_text(
        "metric,value\n" + "\n".join(f"{key},{value}" for key, value in simulation.items()) + "\n"
    )
    return {
        "working_capital_chart": create_working_capital_chart(metrics, figures / "working_capital_efficiency.svg"),
        "liquidity_chart": create_liquidity_chart(forecast, scenarios, THRESHOLD, figures / "liquidity_stress_test.svg"),
    }


if __name__ == "__main__":
    created = run()
    print("Analytics report created:")
    for name, path in created.items():
        print(f"- {name}: {path.relative_to(PROJECT_DIR)}")
