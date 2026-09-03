import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from cash_forecast import load_default_forecast
from scenario_analysis import monte_carlo_liquidity, run_liquidity_scenarios
from working_capital import load_default_data


def test_working_capital_metrics_have_expected_columns():
    metrics = load_default_data()
    assert len(metrics) == 6
    assert {"dso", "dio", "dpo", "cash_conversion_cycle", "net_working_capital"} <= set(metrics.columns)
    assert (metrics["cash_conversion_cycle"] > 0).all()


def test_forecast_and_monte_carlo_are_reproducible():
    forecast = load_default_forecast()
    assert forecast["closing_cash"].iloc[-1] > 0
    first = monte_carlo_liquidity(forecast, simulations=100, seed=7)
    second = monte_carlo_liquidity(forecast, simulations=100, seed=7)
    assert first == second
    assert len(run_liquidity_scenarios(forecast)) == 9
