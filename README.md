# Polymarket Nvidia CEO Forecast Entry

This entry forecasts Polymarket Yes prices for the `polymarket-nvidia-ceo-forecast-01` competition.

## Model Description

The forecasting model is designed around the structure of mutually exclusive prediction market prices:
- **Median**: The market's last price is pulled toward the cross-market no-arbitrage level (`price / sum of all markets' last prices`) with a strength of 0.75 and an exponential time constant of 60 minutes.
- **Spread & Quantiles**: An asymmetric random-walk widening around the median using quantiles `[0.05, 0.25, 0.5, 0.75, 0.95]` mapped to z-multipliers `[-2.5, -0.15, 0.0, 0.15, 1.0]`. The 25%/75% quantiles sit nearly on the median because stable prices rarely move, while the downside tail is fatter.
- **Volatility ($\sigma_i$)**: Per-market empirical volatility is derived from the 5%-95% range of 60-minute price changes over the last 12 hours, shrunk 50/50 toward a global baseline of 0.0015 and clamped to `[0.0001, 0.006]`.
- **Frozen Markets**: If a market's price has not moved at all in the last 120 minutes, its volatility is multiplied by 0.2 to reflect continued stillness.

## Practice Results

- **Practice Pinball Loss**: 0.283133
- **House Baseline Loss**: 0.363589
- **Improvement**: ~22% lower loss (beating the baseline on all 6 practice cases individually).

## How to Run

```bash
export MAKEFUN_INPUT_DIR=/path/to/input
export MAKEFUN_OUTPUT_DIR=/path/to/output
python3 main.py
```
