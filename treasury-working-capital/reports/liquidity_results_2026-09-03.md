# Liquidity Stress & Monte Carlo Results

Generated from the repository's synthetic treasury cash-flow dataset using an opening cash balance of $1,500,000, a liquidity threshold of $1,000,000, 10,000 Monte Carlo simulations, seed 42, and 12% daily volatility.

## Base forecast

- Minimum closing cash: **$1,000,000**
- Final closing cash: **$3,070,000**
- Base-case threshold breach: **No** (the model uses `< threshold`)

## Stress-test results

| Collection shock | Outflow shock | Minimum cash | Threshold breached |
|---:|---:|---:|:---:|
| 0% | 0% | $1,000,000 | No |
| 0% | +5% | $969,000 | Yes |
| 0% | +10% | $938,000 | Yes |
| -5% | 0% | $994,000 | Yes |
| -5% | +5% | $963,000 | Yes |
| -5% | +10% | $932,000 | Yes |
| -10% | 0% | $988,000 | Yes |
| -10% | +5% | $957,000 | Yes |
| -10% | +10% | $926,000 | Yes |

**Stress scenario breach rate: 8/9 = 88.89%.**

## Monte Carlo results

- Simulations: **10,000**
- Breach probability: **49.86%**
- P05 minimum cash: **$900,805.23**
- Median minimum cash: **$1,000,171.55**
- Simulated minimum cash range: **$784,653.85 to $1,206,481.21**

## Interpretation

The base forecast finishes comfortably above the threshold, but the first modest downside shocks create threshold breaches. The Monte Carlo model indicates material tail liquidity risk: approximately half of simulated paths breach the $1 million threshold, while the 5th-percentile minimum cash balance falls to about $0.901 million.

The existing analytics workflow also generates the liquidity stress-test SVG and Monte Carlo summary tables under `reports/figures/` and `reports/tables/`.
