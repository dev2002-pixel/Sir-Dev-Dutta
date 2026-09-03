# Treasury Working Capital Analytics

A compact Python portfolio project for measuring working-capital efficiency and assessing short-term liquidity risk. It uses **entirely synthetic data** designed to resemble a mid-sized operating company; it does not contain real company, customer, or banking information.

## What it does

- Calculates **DSO, DIO, DPO, cash conversion cycle (CCC), and net working capital (NWC)** from monthly balance and income-statement data.
- Builds a dated, rolling cash-balance forecast from signed cash transactions.
- Runs a grid of collection and disbursement stress cases against a liquidity threshold.
- Runs a reproducible Monte Carlo simulation to estimate the probability of a liquidity-threshold breach.

## Project layout

```text
treasury-working-capital/
├── data/                 # Clearly labelled synthetic CSV inputs
├── src/
│   ├── working_capital.py
│   ├── cash_forecast.py
│   └── scenario_analysis.py
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
python -m pytest
```

## Metric definitions

All monthly flows are annualised using a 365-day convention.

| Metric | Formula |
| --- | --- |
| DSO | Accounts receivable / annualised sales × 365 |
| DIO | Inventory / annualised COGS × 365 |
| DPO | Accounts payable / annualised COGS × 365 |
| CCC | DSO + DIO − DPO |
| NWC | Accounts receivable + inventory − accounts payable |

## Assumptions and interpretation

The sample cash forecast begins with $1.5m of cash and applies transactions on their stated dates. Scenario analysis applies percentage shocks to positive cash flows (collections) and negative cash flows (outflows); a breach means cash falls below the selected threshold. The Monte Carlo model applies independent normal shocks to daily net cash flow. It is an illustrative planning tool, not a production liquidity model or investment recommendation.

## Extending the project

Replace the synthetic CSVs with approved internal data, reconcile opening balances to the general ledger, add customer/supplier payment behaviour, and calibrate shocks from historical volatility before using it for decisions.
