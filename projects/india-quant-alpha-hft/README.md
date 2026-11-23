# Indian Equity & Index Futures: Quantitative Alpha Research and HFT Simulator

A reproducible research project connecting:
- **MF840 Financial Econometrics:** OLS hedge-ratio estimation, Engle-Granger cointegration diagnostics, spread construction and z-score signals.
- **MF796 Computational Methods:** numerical estimation, vectorized calculations and reproducible research workflow.
- **MF821 High-Frequency Trading:** simplified order-book execution, spread, displayed depth, market impact and order-flow imbalance.

> **Data note:** the included sample generator creates synthetic data. It is for pipeline validation only, not actual NSE prices or evidence of a profitable strategy.

## Quick start

Python 3.10+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_sample_data.py
PYTHONPATH=src python -m india_quant.run_pipeline
PYTHONPATH=src pytest -q
```

The pipeline writes an out-of-sample backtest CSV, summary JSON and equity-curve chart under `outputs/`.

## Methodology

1. Estimate the log-price hedge ratio on the first 60% of observations.
2. Run an Engle-Granger diagnostic on the training sample.
3. Calculate the residual spread and trailing z-score on the holdout sample.
4. Enter at |z| >= 2 and exit at |z| <= 0.5.
5. Lag positions one bar and deduct a configurable turnover cost.
6. Separately estimate marketable-order fills from a top-of-book snapshot.

The execution simulator is educational: it is not a queue-position, matching-engine or latency-accurate HFT simulator. The daily-bar cost model is not a full Indian exchange fee/tax/impact model.

## Repository layout

- `generate_sample_data.py` — deterministic synthetic sample generator
- `src/india_quant/` — data validation, econometrics, backtest, metrics and execution modules
- `tests/` — unit tests
- `requirements.txt` — dependencies

## Next research steps

- Replace synthetic observations with licensed, timestamped NSE cash/futures data.
- Add expiry rolls, contract multipliers, lot sizes, fees and realistic bid/ask history.
- Run rolling walk-forward validation and parameter/cost sensitivity.
- Add structural-break and regime analysis.
- Use event-level order-book data for partial fills, queue priority and adverse-selection analysis.

**No profitability claim is made.** Any market conclusion requires clean real data, robust out-of-sample testing and realistic costs.
