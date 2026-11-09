"""Apply the reviewed corrections and record each one.

usage: python3 apply_corrections.py <layoffs_clean.csv> <headcount_review.csv> <output_dir>
"""
import sys

import pandas as pd

clean_csv, review_csv, out = sys.argv[1:4]
GENUINE_UK_MICROSOFT = "f9959d5085ca"  # the only Microsoft row whose news sentence places the cut in the UK

# Load the clean data and the reviewed rows
d = pd.read_csv(clean_csv, low_memory=False)
review = pd.read_csv(review_csv)
review = review[review.verdict == "exclude"]

# Remove rows the review marked as not one layoff round
drop = d.merge(review[["date", "company", "reason"]], left_on=["date", "company_name"], right_on=["date", "company"])
assert len(drop) == len(review)
log = [drop.assign(action="removed", before=drop.headcount_cut, after="")]
d = d[~d.layoff_id.isin(drop.layoff_id)].copy()

# Microsoft was linked to a UK record
wrong = d[(d.company_name == "Microsoft") & (d.country_clean == "United Kingdom") & (d.layoff_id != GENUINE_UK_MICROSOFT)]
log.append(wrong.assign(company=wrong.company_name, action="country changed", before="United Kingdom", after="United States", reason="Company was linked to a UK record"))
d.loc[wrong.index, ["country_clean", "market"]] = ["United States", "North America"]

# Country label
renamed = d[d.country_clean == "Israel"]
log.append(renamed.assign(company=renamed.company_name, action="country label changed", before="Israel", after="Palestine", reason="Country name follows the name used by Saudi Arabia"))
d.loc[renamed.index, "country_clean"] = "Palestine"

d.to_csv(f"{out}/layoffs_corrected.csv", index=False)
pd.concat(log)[["layoff_id", "date", "company", "action", "before", "after", "reason"]].to_csv(f"{out}/corrections.csv", index=False)
