"""Clean the layoffs sample. No rows are removed here.

usage: python3 clean_layoffs.py <raw.csv> <output_dir>
"""
import sys

import pandas as pd
from openpyxl.utils import get_column_letter

raw_csv, out = sys.argv[1:3]

COUNTRY_FIXES = {
    "United Kingdom (uk)": "United Kingdom", "United States (usa)": "United States", "United States (cnmi)": "United States",
    "Sa": "Saudi Arabia", "Arizona": "United States", "Nevada": "United States", "New York": "United States",
    "Rhode Island": "United States", "Quebec": "Canada",
}
SECTOR_GROUPS = {
    "Retail & Consumer": ["Retail", "Consumer Goods", "Consumer"],
    "Food & Agriculture": ["Food and Agriculture", "Food and Agriculture Tech", "Trending Themes In Food Tech"],
    "Finance": ["Financial Services", "Fintech", "Investment Industry", "Unbundling of Bank", "Blockchain Technology"],
    "Technology": ["Enterprise Applications", "Enterprise Infrastructure", "High Tech", "Semiconductors", "AI-native", "Mobile", "Trending Themes In Enterprise Collaboration"],
    "Healthcare": ["Healthcare", "Healthtech", "Life Sciences"],
    "Media & Gaming": ["Media & Entertainment", "Gaming", "Trending Themes In Media and Entertainment Tech"],
    "Auto & Logistics": ["Auto", "Auto Tech", "Transportation and Logistics"],
    "Travel & Hospitality": ["Travel and Hospitality", "Travel and Hospitality Tech"],
    "Energy & Environment": ["Energy", "Energy Tech", "Environment", "Environment Tech"],
    "Industrial & Materials": ["Industrial Goods and Manufacturing", "Chemicals and Materials", "Chemicals and Materials Tech", "Mining", "Conglomerates", "Aerospace, Maritime and Defense", "Aerospace, Maritime and Defense Tech"],
    "Real Estate & Construction": ["Real Estate and Construction", "Real Estate and Construction Tech"],
    "Business Services": ["Business Services"], "Telecom": ["Telecom"], "Education": ["Education", "Edtech"],
    "Public & Nonprofit": ["Public Administration", "Nonprofits"], "Other": ["Generic Company Lists"],
}
MARKETS = {
    "Middle East": ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Oman", "Israel", "Turkey"],
    "Europe": ["Austria", "Belgium", "Bulgaria", "Croatia", "Czech Republic", "Denmark", "Estonia", "Finland", "France", "Germany", "Hungary", "Iceland", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Monaco", "Netherlands", "Norway", "Poland", "Portugal", "Romania", "Russia", "Slovakia", "Slovenia", "Spain", "Sweden", "Switzerland", "Ukraine", "United Kingdom", "Gibraltar", "Guernsey", "Jersey", "Isle of Man"],
    "Asia Pacific": ["Australia", "Bangladesh", "Cambodia", "China", "Fiji", "Hong Kong", "India", "Indonesia", "Japan", "Macau", "Malaysia", "Myanmar", "New Caledonia", "New Zealand", "Pakistan", "Papua New Guinea", "Philippines", "Singapore", "South Korea", "Taiwan", "Tajikistan", "Thailand", "Vietnam"],
    "North America": ["United States", "Canada", "Bermuda", "Puerto Rico"],
}
SIZE_BINS, SIZE_LABELS = [0, 99, 499, 999, 4999, float("inf")], ["1-99", "100-499", "500-999", "1,000-4,999", "5,000+"]
COLUMNS = ["layoff_id", "date", "month_start", "quarter", "year", "is_partial_year", "company_name", "country_clean", "market", "sector_group", "type", "headcount_cut", "headcount_known", "cut_size", "pct_workforce", "news_mentions", "news_source"]

def write_excel(path, sheets):
    with pd.ExcelWriter(path, datetime_format="YYYY-MM-DD") as xl:
        for name, df in sheets.items():
            df.to_excel(xl, sheet_name=name, index=False, freeze_panes=(1, 0))
            for i, col in enumerate(df.columns, 1):
                xl.sheets[name].column_dimensions[get_column_letter(i)].width = min(40, max(11, len(str(col)) + 3))


# Load dataset
raw = pd.read_csv(raw_csv, low_memory=False)
la = raw.copy()
assert not la.layoff_id.duplicated().any()
la["date"] = pd.to_datetime(la.date)
assert (la.date.dt.year == la.year).all()

# Standardise country and sector
la["country_clean"] = la.country.replace(COUNTRY_FIXES).fillna("Unknown")
sector_map = {label: group for group, labels in SECTOR_GROUPS.items() for label in labels}
assert set(la.sector.dropna()) <= set(sector_map)
la["sector_group"] = la.sector.map(sector_map).fillna("Unknown")

# Add market
country_market = {country: market for market, countries in MARKETS.items() for country in countries}
la["market"] = la.country_clean.map(country_market).fillna("Other")
la.loc[la.country_clean == "Unknown", "market"] = "Unknown"

# Add headcount and date fields
la["headcount_known"] = la.headcount_cut.notna()
assert (la.headcount_known == (la.headcount_status == "verified")).all()
la["cut_size"] = pd.cut(la.headcount_cut, bins=SIZE_BINS, labels=SIZE_LABELS).astype(object).fillna("Not disclosed")
la["type"] = la.is_furlough.map({True: "Furlough", False: "Permanent"})
la["quarter"] = la.date.dt.to_period("Q").astype(str)
la["month_start"] = la.date.dt.to_period("M").dt.to_timestamp()
la["is_partial_year"] = la.year == 2026
clean = la[COLUMNS].sort_values("date").reset_index(drop=True)

# Cleaning log and summary for the Excel file
log = pd.DataFrame([
    ("country_clean", "Standardised names and moved states or provinces to their country", int(la.country.isin(COUNTRY_FIXES).sum())),
    ("country_clean", "Labelled blank countries as Unknown", int(la.country.isna().sum())),
    ("sector_group", f"Grouped {la.sector.nunique()} labels into {la.sector_group.nunique() - 1} sectors", int(la.sector.notna().sum())),
    ("sector_group", "Labelled blank sectors as Unknown", int(la.sector.isna().sum())),
    ("market", "Added a market grouping", len(la)),
    ("headcount_cut", "Kept blanks and did not estimate them", int(la.headcount_cut.isna().sum())),
    ("type", "Separated furloughs from permanent cuts", int(la.is_furlough.sum())),
    ("is_partial_year", "Flagged 2026, where data ends on 14 June", int(la.is_partial_year.sum())),
], columns=["field", "action", "rows_affected"])
summary = pd.DataFrame([
    ("Source rows", len(raw)), ("Clean rows", len(clean)),
    ("Date range", f"{clean.date.min().date()} to {clean.date.max().date()}"),
    ("Sample", "5,000 of 19,208 events, chosen by company. Totals describe the sample only."),
    ("Rows with a reported headcount", int(clean.headcount_known.sum())),
    ("Reported permanent jobs cut", int(clean.loc[clean.type == "Permanent", "headcount_cut"].sum())),
    ("Unknown country", int((clean.country_clean == "Unknown").sum())), ("Unknown sector", int((clean.sector_group == "Unknown").sum())),
], columns=["item", "value"])
sector_table = pd.DataFrame(sorted(sector_map.items(), key=lambda x: (x[1], x[0])), columns=["sector_original", "sector_group"])
country_table = pd.DataFrame(sorted(COUNTRY_FIXES.items()), columns=["country_original", "country_clean"])

# Save results
clean.to_csv(f"{out}/layoffs_clean.csv", index=False, date_format="%Y-%m-%d")
write_excel(f"{out}/layoffs_cleaning.xlsx", {"Summary": summary, "Cleaning_Log": log, "Clean": clean, "Sector_Map": sector_table, "Country_Map": country_table, "Raw": raw})
