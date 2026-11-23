# NSE × Reliance Industries: market-impact research design

## Research objective

Estimate how Reliance Industries (NSE symbol: `RELIANCE`) is associated with
the Indian equity market, and distinguish its **mechanical index contribution**
from its **statistical relationship** with market returns.

NIFTY 50 is free-float market-cap weighted. A constituent's contribution
therefore depends on its investible/free-float weight, not simply its full
market capitalization. Obtain historical constituent weights from NSE Indices
for each rebalance/month; do not apply today's weight to the entire history.

## Universe

- Reliance Industries: `RELIANCE.NS`
- NIFTY 50: `^NSEI`
- NIFTY Bank: `^NSEBANK`
- NIFTY Energy: `^CNXENERGY` (provider symbol availability must be checked)

Yahoo Finance data is a convenient research proxy, not official NSE tick data.
For publishable work, replace it with licensed NSE/vendor adjusted prices,
index total-return data, corporate actions and timestamped announcements.

## Tests and estimators

1. Daily log returns and rolling 20/60/120-session correlations.
2. OLS: market return on Reliance return, with Newey-West/HAC standard errors.
3. Lead-lag regressions: market return at t on Reliance return at t-k, k in
   {1,2,3,5}; also test the reverse direction and control for market return.
4. Mechanical NIFTY contribution approximation:
   `contribution_t ≈ weight_t × Reliance_return_t`.
5. Approximate NIFTY excluding Reliance:
   `r_ex_RIL ≈ (r_NIFTY - weight × r_RIL)/(1-weight)`.
   This is a first-order approximation. Exact attribution requires official
   index methodology, constituent weights, divisor and corporate-action data.
6. Event study around dated company announcements: [-1,+1] and [0,+2] sessions.
   Curate events from the official investor-relations announcement archive and
   use the actual exchange filing timestamp to define the event session.

## Interpretation safeguards

- Correlation is not causation; a high correlation may reflect common market
  exposure and Reliance's index weight.
- The regression beta measures conditional co-movement, not causal influence.
- A lagged coefficient is not automatically tradable alpha; account for
  information timing, serial correlation, multiple testing and transaction costs.
- Report confidence intervals, sample period, observations, missing-data rules,
  corporate-action treatment and out-of-sample results.
- Do not claim that Reliance "moves the market" unless the evidence supports a
  carefully qualified attribution statement.

## Data files

- `data/reliance_index_weights_template.csv`: fill with official historical
  NIFTY 50 constituent weights, in percentage points, dated as published.
- `data/reliance_events_template.csv`: replace/add verified announcement dates.

## Run

```bash
pip install -r requirements.txt
python nse_reliance_analysis.py --start 2018-01-01
python nse_reliance_analysis.py --start 2018-01-01 \
  --weights data/reliance_index_weights.csv \
  --events data/reliance_events.csv
```

A constant-weight sensitivity run is possible with `--weight-pct`, but must
not be described as historical attribution.
