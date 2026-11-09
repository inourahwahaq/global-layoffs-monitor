"""Forecast monthly layoff events six months ahead.

usage: python3 forecast.py <layoffs_corrected.csv> <output_dir>

Each method is scored from 24 past starting points. The 12 month average is used unless another
method is clearly better. Training stops at April 2026 because news coverage thins after that.
"""
import sys
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")
clean_csv, out = sys.argv[1:3]
HORIZON, ORIGINS, BASE = 6, 24, "Last 12 month average"
rng = np.random.default_rng(2026)

d = pd.read_csv(clean_csv, low_memory=False, parse_dates=["month_start"])
y = d.groupby("month_start").size().asfreq("MS", fill_value=0)
y = y[y.index < "2026-05-01"].astype(float)
n = len(y)


def flat(train, h):
    return np.repeat(train.iloc[-12:].mean(), h)


def seasonal_naive(train, h):
    return train.iloc[-12:].iloc[:h].values


def damped_trend(train, h):
    fit = ExponentialSmoothing(np.log1p(train), trend="add", damped_trend=True, initialization_method="estimated").fit()
    return np.expm1(fit.forecast(h).values)


def holt_winters(train, h):
    fit = ExponentialSmoothing(np.log1p(train), trend="add", damped_trend=True, seasonal="add", seasonal_periods=12, initialization_method="estimated").fit()
    return np.expm1(fit.forecast(h).values)


def sarima(train, h):
    fit = SARIMAX(np.log1p(train), order=(0, 1, 1), seasonal_order=(0, 1, 1, 12), enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    return np.expm1(fit.forecast(h).values)


MODELS = {BASE: flat, "Same month last year": seasonal_naive, "Damped trend": damped_trend, "Holt-Winters": holt_winters, "SARIMA": sarima}


def backtest(name, model, ends):
    rows = []
    for end in ends:
        test = y.iloc[end:end + HORIZON]
        predictions = np.maximum(model(y.iloc[:end], HORIZON), 0)
        for month, actual, predicted in zip(test.index, test.values, predictions):
            rows.append({"model": name, "end": end, "month": month, "actual": actual, "forecast": predicted})
    return pd.DataFrame(rows).assign(abs_error=lambda t: (t.actual - t.forecast).abs())


# Score every method from the same 24 starting points
ends = range(n - HORIZON - ORIGINS + 1, n - HORIZON + 1)
by_origin = pd.concat([backtest(k, f, ends) for k, f in MODELS.items()]).groupby(["model", "end"]).abs_error.mean().unstack(0)
score = pd.DataFrame({"mae": by_origin.mean().round(2)})
for name in MODELS:
    gain = (by_origin[BASE] - by_origin[name]).values
    draws = [rng.choice(gain, len(gain)).mean() for _ in range(5000)]
    low = round(np.percentile(draws, 2.5), 2)
    high = round(np.percentile(draws, 97.5), 2)
    score.loc[name, ["gain_vs_average", "gain_low", "gain_high"]] = round(gain.mean(), 2), low, high
score = score.sort_values("mae")
clear = score[score.gain_low > 0]
chosen = clear.index[0] if len(clear) else BASE

# Range: the 10th to 90th percentile of past error ratios. Starts after the 2020 shock has left the 12 month level.
past = backtest(chosen, MODELS[chosen], range(48, n - HORIZON + 1)).assign(ratio=lambda t: (t.actual + 1) / (t.forecast + 1))
hits = []
for end in sorted(past.end.unique()):
    known = past[past.month <= y.index[end - 1]]
    if len(known) >= 30:
        cur = past[past.end == end]
        low, high = known.ratio.quantile(.10), known.ratio.quantile(.90)
        actual = cur.actual + 1
        predicted = cur.forecast + 1
        hits += ((actual >= predicted * low) & (actual <= predicted * high)).tolist()

# Final forecast
low, high = past.ratio.quantile(.10), past.ratio.quantile(.90)
fc = np.maximum(MODELS[chosen](y, HORIZON), 0)
months = pd.date_range(y.index[-1] + pd.offsets.MonthBegin(1), periods=HORIZON, freq="MS")
forecast = pd.DataFrame({"month": months, "forecast": fc.round(1), "low_80": ((fc + 1) * low - 1).clip(0).round(1), "high_80": ((fc + 1) * high - 1).round(1)})
totals = past.groupby("end").agg(a=("actual", "sum"), f=("forecast", "sum"))
ratio = totals.a / totals.f
summary = pd.DataFrame([{
    "model": chosen,
    "total": round(fc.sum()),
    "total_low": round(fc.sum() * ratio.quantile(.10)),
    "total_high": round(fc.sum() * ratio.quantile(.90)),
    "unseen_month_hit_rate_pct": round(np.mean(hits) * 100, 1),
    "unseen_months": len(hits),
    "mae": score.loc[chosen, "mae"],
}])

y.rename("events").rename_axis("month").reset_index().to_csv(f"{out}/monthly_actual.csv", index=False)
forecast.to_csv(f"{out}/forecast.csv", index=False)
score.to_csv(f"{out}/forecast_backtest.csv")
summary.to_csv(f"{out}/forecast_summary.csv", index=False)
