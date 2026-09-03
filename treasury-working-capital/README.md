# Treasury Working Capital Analytics

A compact Python portfolio project for measuring working-capital efficiency and assessing short-term liquidity risk. It uses **entirely synthetic data** designed to resemble a mid-sized operating company; it does not contain real company, customer, or banking information.

## Executive Treasury Risk Dashboard

This dashboard brings **Monte Carlo liquidity risk and SOFR forecasting together** so the reader can see liquidity downside and interest-rate risk in one view.

| Liquidity Risk | Interest-Rate Risk |
| --- | --- |
| ![Monte Carlo liquidity paths](reports/figures/monte_carlo_paths.png) | ![SOFR forecast](reports/figures/sofr_forecast.svg) |
| ![Minimum cash distribution](reports/figures/monte_carlo_minimum_cash.png) | ![SOFR sensitivity](reports/figures/sofr_sensitivity.svg) |

### Current model snapshot

| Metric | Result |
| --- | ---: |
| Liquidity threshold | $1.00M |
| Monte Carlo simulations | 10,000 |
| Daily cash-flow volatility | 12% |
| Monte Carlo breach probability | 49.86% |
| P05 minimum cash | $900,805 |
| Median minimum cash | $1,000,172 |

The Monte Carlo model uses a fixed seed of 42 for reproducibility. The SOFR model uses a transparent AR(1) forecast with a six-month horizon and prediction interval. Both analyses are illustrative because the bundled dataset is synthetic.

## What it does

- Calculates **DSO, DIO, DPO, cash conversion cycle (CCC), and net working capital (NWC)** from monthly balance and income-statement data.
- Builds a dated, rolling cash-balance forecast from signed cash transactions.
- Runs a grid of collection and disbursement stress cases against a liquidity threshold.
- Runs a reproducible Monte Carlo simulation to estimate the probability of a liquidity-threshold breach.
- Produces Monte Carlo path, minimum-cash distribution, and percentile-band visualizations.
- Forecasts **SOFR** with a transparent AR(1) model and a 95% prediction interval.
- Measures descriptive SOFR relationships with DSO, DIO, DPO, CCC and NWC.
- Runs SOFR shock sensitivity for illustrative floating-rate interest expense.
- Produces reusable CSV report tables and presentation-ready charts through one command.
- Adds an illustrative bank-credit review of leverage, coverage, liquidity, covenant headroom, stress sensitivity, and refinancing timing.

## Project layout

```text
treasury-working-capital/
├── data/                 # Clearly labelled synthetic CSV inputs
├── src/
│   ├── working_capital.py
│   ├── cash_forecast.py
│   ├── scenario_analysis.py
│   ├── liquidity_visualizations.py # Monte Carlo liquidity charts
│   ├── credit_risk.py
│   ├── sofr_analysis.py             # SOFR forecasting + sensitivity
│   ├── sofr_visualizations.py       # SOFR graphical analysis
│   ├── visualizations.py
│   └── main_analytics.py
├── reports/              # Generated tables and GitHub-viewable charts
├── tests/
├── requirements.txt
└── README.md
```

## Quick start

```bash
cd treasury-working-capital
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python src/working_capital.py
python src/cash_forecast.py
python src/scenario_analysis.py
python src/main_analytics.py
python -m pytest
```

## Analytics report

Run `python src/main_analytics.py` to regenerate the files in `reports/`. The command writes working-capital, liquidity, credit-risk and SOFR CSV tables, plus presentation-ready charts.

### Working-capital trend

![Working-capital efficiency](reports/figures/working_capital_efficiency.svg)

### Liquidity stress test

![Liquidity stress test](reports/figures/liquidity_stress_test.svg)

### Monte Carlo liquidity paths

![Monte Carlo paths](reports/figures/monte_carlo_paths.png)

### Monte Carlo minimum-cash distribution

![Monte Carlo distribution](reports/figures/monte_carlo_minimum_cash.png)

### Liquidity percentile bands

![Liquidity fan chart](reports/figures/liquidity_fan_chart.png)

### SOFR forecast

![SOFR forecast](reports/figures/sofr_forecast.svg)

### SOFR relationships

![SOFR relationships](reports/figures/sofr_relationships.svg)

### SOFR interest-rate sensitivity

![SOFR sensitivity](reports/figures/sofr_sensitivity.svg)

## SOFR methodology

`src/sofr_analysis.py` uses a deliberately transparent AR(1) model:

**SOFR(t) = α + β × SOFR(t−1) + ε(t)**

The bundled monthly observations are synthetic. The model produces a six-month point forecast and a simple 95% prediction interval based on the historical regression residual volatility. This is a portfolio demonstration rather than a production interest-rate forecast.

The relationship analysis joins the synthetic SOFR series to the project's monthly working-capital metrics and reports Pearson correlations. These correlations are **descriptive, not causal**. The sensitivity analysis translates SOFR shocks into annual interest expense for illustrative $5m, $10m and $25m floating-rate balances.

## Liquidity and Monte Carlo methodology

The deterministic stress test applies collection shocks and outflow shocks independently. The Monte Carlo model applies independent normal shocks to each daily net cash flow and calculates the minimum cash balance for every simulated path. The dashboard reports breach probability, P05 minimum cash and median minimum cash. The simulation is deterministic for a given seed, which makes the results reproducible.

## Bank credit and default-risk perspective

The `data/credit_inputs.csv` file is the borrower input sheet. It captures synthetic debt, cash, undrawn facility, EBITDA, interest, debt service, maturity, and covenant limits. `src/credit_risk.py` evaluates the following bank-review inputs:

| Credit input | Bank-review purpose |
| --- | --- |
| Net leverage | Debt burden relative to recurring earnings |
| Interest coverage | Capacity to pay interest from earnings |
| Debt-service coverage | Capacity to pay contractual debt service |
| Minimum cash and undrawn facility | Liquidity cushion and reliance on committed funding |
| Liquidity stress cases | Resilience when collections fall or outflows rise |
| Debt maturity | Refinancing risk and time available to address it |
| Covenant limits | Early-warning signals and contractual headroom |

The resulting `credit_tests.csv` and `credit_risk_summary.csv` are written to `reports/tables/`. The **indicative risk score is not a probability of default (PD)** and must not be used as a lending decision, rating, or regulatory model. A real bank would calibrate PD using historical defaults, borrower-specific cash flows, collateral, sector conditions, legal documentation, and its own credit policy.

## Assumptions and interpretation

The sample cash forecast begins with $1.5m of cash and applies transactions on their stated dates. Scenario analysis applies percentage shocks to positive cash flows (collections) and negative cash flows (outflows); a breach means cash falls below the selected threshold. The Monte Carlo model applies independent normal shocks to daily net cash flow. The credit review prioritises repayment capacity under stress, consistent with supervisory credit-risk principles. It is an illustrative planning tool, not a production liquidity model, lending decision, or investment recommendation.

## Automated dashboard publishing

A GitHub Actions workflow in `.github/workflows/treasury-analytics.yml` runs the analytics pipeline when the Treasury project changes or when manually dispatched. It installs the project dependencies, regenerates the Monte Carlo and SOFR charts/tables, runs the test suite, and commits refreshed report outputs back to the repository.

## Extending the project

Replace the synthetic CSVs with approved internal data, add an official SOFR data feed such as the Federal Reserve Bank of New York's published series, consider OLS/ARIMA/state-space models and out-of-sample backtesting, and calibrate rate shocks from historical volatility before using it for decisions.
