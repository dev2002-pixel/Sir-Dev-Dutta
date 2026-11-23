# Indian Equity & Index Futures: Quantitative Alpha Research and HFT Simulator

A reproducible research project connecting:
- **MF840 Financial Econometrics:** OLS hedge-ratio estimation, Engle-Granger cointegration diagnostics, spread construction and z-score signals.
- **MF796 Computational Methods:** numerical estimation, vectorized calculations and reproducible research workflow.
- **MF821 High-Frequency Trading:** simplified order-book execution, spread, displayed depth, market impact and order-flow imbalance.
- **NSE × Reliance market impact:** Reliance Industries' co-movement with NIFTY 50, NIFTY Bank and NIFTY Energy; HAC regressions, lead-lag tests, event studies and weight-based NIFTY contribution estimates.

> **Data note:** the included sample generator creates synthetic data. The NSE/Reliance module downloads Yahoo Finance adjusted-price proxies. Neither source is official exchange-grade tick data or evidence of a profitable strategy.

## Quick start

Python 3.10+:

~~~bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_sample_data.py
PYTHONPATH=src python -m india_quant.run_pipeline
PYTHONPATH=src pytest -q
~~~

## NSE × Reliance analysis

The additional research module downloads:
- Reliance Industries: RELIANCE.NS
- NIFTY 50: ^NSEI
- NIFTY Bank: ^NSEBANK
- NIFTY Energy: ^CNXENERGY (if available from the data provider)

Run the daily market-linkage analysis:

~~~bash
python nse_reliance_analysis.py --start 2018-01-01
~~~

For historical index attribution, first populate an official historical
constituent-weight file using the schema in
data/reliance_index_weights_template.csv, then run:

~~~bash
python nse_reliance_analysis.py --start 2018-01-01 --weights data/reliance_index_weights.csv --events data/reliance_events.csv
~~~

Outputs include daily log returns, a correlation matrix, HAC-robust market
regressions, lagged-return regressions, and (when official weights are supplied)
an estimated Reliance contribution and NIFTY-ex-Reliance return series.
See NSE_RELIANCE_RESEARCH.md for equations, interpretation safeguards and data requirements.

**Important:** correlation and regression beta measure co-movement, not causal
influence. A lagged coefficient is not automatically tradable alpha. NIFTY
contribution is a first-order approximation; exact attribution requires
official constituent weights and index calculation data. Yahoo Finance is
only a convenient research proxy; validate results with licensed NSE/vendor
data before presenting market conclusions.

## Original strategy methodology

1. Estimate the log-price hedge ratio on the first 60% of observations.
2. Run an Engle-Granger diagnostic on the training sample.
3. Calculate the residual spread and trailing z-score on the holdout sample.
4. Enter at |z| >= 2 and exit at |z| <= 0.5.
5. Lag positions one bar and deduct a configurable turnover cost.
6. Separately estimate marketable-order fills from a top-of-book snapshot.

The execution simulator is educational: it is not a queue-position,
matching-engine or latency-accurate HFT simulator. The daily-bar cost model is
not a full Indian exchange fee/tax/impact model.

## Repository layout

- generate_sample_data.py — deterministic synthetic sample generator
- nse_reliance_analysis.py — NSE/Reliance market-linkage research
- NSE_RELIANCE_RESEARCH.md — research design and interpretation guide
- data/ — historical index-weight and corporate-event templates
- src/india_quant/ — data validation, econometrics, backtest, metrics and execution modules
- tests/ — unit tests
- requirements.txt — dependencies

## Next research steps

- Replace synthetic/Yahoo observations with licensed, timestamped NSE cash/futures data.
- Obtain monthly official NIFTY 50 constituent weights and account for rebalances.
- Add expiry rolls, contract multipliers, lot sizes, fees and realistic bid/ask history.
- Run rolling walk-forward validation and parameter/cost sensitivity.
- Add structural-break and regime analysis.
- Use event-level order-book data for partial fills, queue priority and adverse-selection analysis.

**No profitability or causal-impact claim is made.**
