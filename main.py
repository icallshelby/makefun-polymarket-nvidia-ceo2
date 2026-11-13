# polymarket-nvidia-ceo-forecast-01 entry (Python 3.13, standard library only).
# Full rewrite with the requested improvement: standard normal quantile fallback
# for non-standard quantile levels using Acklam's rational approximation.

import json
import math
import os
from pathlib import Path

INPUT_DIR = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
OUTPUT_DIR = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")

# Tuned z-multipliers for the 5 standard contest quantile levels
Z_BY_TAU = {0.05: -2.5, 0.25: -0.15, 0.5: 0.0, 0.75: 0.15, 0.95: 1.0}
SIGMA_GLOBAL = 0.0015
SIGMA_MIN = 0.0001
SIGMA_MAX = 0.006
SHRINK_W = 0.5
RECENT_MIN = 720
H60 = 60
FROZEN_MIN = 120
FROZEN_SHRINK = 0.2
SUM_STRENGTH = 0.75
SUM_TAU_MIN = 60.0


def normal_inverse_cdf(p):
    """Peter J. Acklam's rational approximation for standard normal inverse CDF."""
    if p <= 0.0:
        return -float('inf')
    if p >= 1.0:
        return float('inf')

    a = [-3.969683028665376e+01,  2.209460984245205e+02,
         -2.759285104469687e+02,  1.383577518672690e+02,
         -3.066479806614716e+01,  2.506628277459239e+00]
    b = [-5.447609879822406e+01,  1.615858368580409e+02,
         -1.556989798598866e+02,  6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00,  2.938163982698783e+00]
    d = [ 7.784695709041462e-03,  3.224671290700398e-01,
         2.445134137142996e+00,  3.754408661907416e+00]

    low = 0.02425
    high = 1.0 - low

    if p < low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
               ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    elif p > high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
    else:
        q = p - 0.5
        r = q * q
        return ((((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q) / \
               (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)


def get_z(tau):
    """Return tuned z multiplier if available, else standard normal quantile."""
    if tau in Z_BY_TAU:
        return Z_BY_TAU[tau]
    return normal_inverse_cdf(tau)


def quantile(sorted_vals, q):
    """Linear-interpolation quantile."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    w = pos - lo
    return sorted_vals[lo] * (1.0 - w) + sorted_vals[hi] * w


def price6(x):
    """Clamp to [0,1] and round to 6 decimals (0, never -0)."""
    return round(min(1.0, max(0.0, x)) * 1e6) / 1e6 + 0.0


def empirical_sigma(prices):
    """Implied per-sqrt-minute sigma from 60-minute changes."""
    r = prices[-RECENT_MIN:] if len(prices) > RECENT_MIN else prices
    if len(r) <= H60:
        return None
    changes = sorted(r[i + H60] - r[i] for i in range(len(r) - H60))
    spread = quantile(changes, 0.95) - quantile(changes, 0.05)
    return (spread / 2.0) / (1.644854 * math.sqrt(H60))


def is_frozen(prices):
    """True when the price has not moved at all in the last FROZEN_MIN minutes."""
    if len(prices) < FROZEN_MIN:
        return False
    first = prices[-FROZEN_MIN]
    return all(p == first for p in prices[-FROZEN_MIN:])


def forecast_market(prices, last, total, horizon, zvals):
    """One market's forecast: horizon rows of quantiles."""
    sigma_emp = empirical_sigma(prices)
    if sigma_emp is None:
        sigma = SIGMA_GLOBAL
    else:
        sigma = SHRINK_W * sigma_emp + (1.0 - SHRINK_W) * SIGMA_GLOBAL
    if is_frozen(prices):
        sigma *= FROZEN_SHRINK
    sigma = min(max(sigma, SIGMA_MIN), SIGMA_MAX)

    target = last / total if total > 0 else last
    rows = []
    for h in range(1, horizon + 1):
        med = last + SUM_STRENGTH * (target - last) * (1.0 - math.exp(-h / SUM_TAU_MIN))
        s = sigma * math.sqrt(h)
        row = [price6(med + z * s) for z in zvals]
        for j in range(1, len(row)):
            if row[j] < row[j - 1]:
                row[j] = row[j - 1]
        rows.append(row)
    return rows


def forecast_case(case):
    horizon = int(case["horizon_minutes"])
    quantiles = [float(q) for q in case["quantiles"]]
    zvals = [get_z(q) for q in quantiles]
    markets = case["markets"]
    total = sum(float(m["prices"][-1]) for m in markets)
    forecasts = []
    for m in markets:
        prices = [float(p) for p in m["prices"]]
        last = prices[-1]
        forecasts.append({
            "id": m["id"],
            "q": forecast_market(prices, last, total, horizon, zvals),
        })
    return {"forecasts": forecasts}


def main():
    in_dir = Path(INPUT_DIR)
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    for in_file in sorted(in_dir.glob("*.in")):
        case = json.loads(in_file.read_text(encoding="utf-8"))
        out = forecast_case(case)
        out_file = out_dir / (in_file.stem + ".out")
        out_file.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
