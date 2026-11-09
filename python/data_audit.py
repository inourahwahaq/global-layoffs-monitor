"""Test whether the layoffs sample supports the study's claims.

usage: python3 data_audit.py <layoffs_clean.csv> <layoffs_cleaning.xlsx> <output_dir>
"""
import sys

import numpy as np
import pandas as pd

clean_csv, xlsx, out = sys.argv[1:4]
rng = np.random.default_rng(2026)
d = pd.read_csv(clean_csv, low_memory=False, parse_dates=["date", "month_start"])
d = d.merge(pd.read_excel(xlsx, sheet_name="Raw")[["layoff_id", "news_excerpt"]], on="layoff_id")
A0, A1, B0 = pd.Timestamp("2025-05-01"), pd.Timestamp("2026-05-01"), pd.Timestamp("2024-05-01")
now, prior = d[(d.date >= A0) & (d.date < A1)], d[(d.date >= B0) & (d.date < A0)]

# Sample against the publisher's tables for all 19,208 events
FULL_YEAR = {2019: 1759, 2020: 3780, 2021: 1032, 2022: 2008, 2023: 3391, 2024: 3011, 2025: 2977}
years = pd.DataFrame({"sample": d.groupby("year").size(), "full": pd.Series(FULL_YEAR)}).dropna()
years["sample_share_pct"] = (years["sample"] / years.full * 100).round(1)
years.to_csv(f"{out}/sample_vs_full_by_year.csv")

# Headline changes: is each one larger than chance?
def permanent_cuts(window):
    return window[(window.type == "Permanent") & window.headcount_cut.notna()].headcount_cut.values


def interval(function, last, previous):
    ratios = []
    for _ in range(5000):
        ratios.append(function(rng.choice(last, len(last))) / function(rng.choice(previous, len(previous))))
    return np.percentile(ratios, [2.5, 97.5])


x, y = permanent_cuts(now), permanent_cuts(prior)
se = np.sqrt(1 / len(now) + 1 / len(prior))
ratio = len(now) / len(prior)
rows = [("events", len(now), len(prior), ratio, ratio * np.exp(-1.96 * se), ratio * np.exp(1.96 * se))]
rows.append(("reported jobs", x.sum(), y.sum(), x.sum() / y.sum(), *interval(np.sum, x, y)))
rows.append(("median cut", np.median(x), np.median(y), np.median(x) / np.median(y), *interval(np.median, x, y)))
changes = pd.DataFrame(rows, columns=["measure", "last_12m", "prior_12m", "ratio", "ci_low", "ci_high"]).round(3)
changes["clear_of_chance"] = (changes.ci_low > 1) | (changes.ci_high < 1)
changes.to_csv(f"{out}/headline_changes.csv", index=False)

# The 16 largest permanent figures in each window, read against the news sentence
EXCLUDE = {
    ("Technology", "2026-02-05"): "Sector total from a monthly report, not a company",
    ("Intel", "2025-10-08"): "Recap of the whole year, not one round",
    ("Microsoft", "2026-01-01"): "Rumour and estimate, not a layoff",
    ("India’s Tata Consultancy Services", "2025-09-26"): "Year to date total, not one round",
    ("Bosch", "2025-01-31"): "Headcount fall over the past year, not one round",
    ("Coal India", "2024-09-23"): "Headcount fall over a fiscal year, not a layoff",
    ("UBS Social Innovators", "2025-02-04"): "Total since 2023, not one round",
    ("Nissan", "2025-01-25"): "Repeats the 9,000 round of November 2024",
    ("Cognizant", "2024-05-06"): "Headcount fall over a year, not a layoff",
}
CHECK = {
    ("Caterpillar Tractor", "2024-05-02"): "Sentence has no date, the figure may be historic",
    ("Toshiba", "2024-09-13"): "Sentence has no date, the figure may be historic",
}
review = []
for label, window in (("last_12m", now), ("prior_12m", prior)):
    top = window[(window.type == "Permanent") & window.headcount_cut.notna()].sort_values(["headcount_cut", "date"], ascending=False).head(16)
    for r in top.itertuples():
        key = (r.company_name, str(r.date.date()))
        verdict = "exclude" if key in EXCLUDE else "check" if key in CHECK else "keep"
        reason = EXCLUDE.get(key, CHECK.get(key, ""))
        review.append({"window": label, "date": key[1], "company": key[0], "headcount": r.headcount_cut, "verdict": verdict, "reason": reason, "news_excerpt": r.news_excerpt})
pd.DataFrame(review).to_csv(f"{out}/headcount_review.csv", index=False)
