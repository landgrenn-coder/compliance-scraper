"""
filter_violations.py

Filters a merged OSHA inspection+violation dataset for healthcare facilities
cited for bloodborne pathogen, sharps disposal, or hazardous waste violations.

Produces two output CSVs:
  - acute_prospects.csv      — Missouri and Kansas only
  - nationwide_prospects.csv — all other states (MO/KS excluded)

ASSUMED COLUMN NAMES (based on OSHA published bulk data schema):
  These come from joining osha_inspection + osha_violation on 'activity_nr'.
  When scraper.py exists, the merged DataFrame it produces must use these names.

  From osha_inspection:
    activity_nr  — unique inspection ID (join key)
    estab_name   — facility/employer name
    site_address — street address
    site_city    — city
    site_state   — two-letter state abbreviation (e.g. "MO")
    naics_code   — NAICS industry code (healthcare = 62xxxx)
    open_date    — date inspection was opened (YYYY-MM-DD)

  From osha_violation:
    activity_nr  — links back to inspection
    standard     — CFR regulation cited (e.g. "1910.1030")
    issuance_dt  — date citation was issued (YYYY-MM-DD)  <-- used for sorting
    penalty      — proposed penalty in dollars
"""

import pandas as pd
from datetime import date

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

INPUT_FILE = "merged_violations.csv"   # output from scraper.py (not yet written)

ACUTE_STATES = {"MO", "KS"}           # territory covered by acute_prospects.csv

# NAICS codes for healthcare (all codes starting with 62)
HEALTHCARE_NAICS_PREFIX = "62"

# CFR standards to keep — add or remove entries here as needed
TARGET_STANDARDS = [
    "1910.1030",   # Bloodborne pathogens
    "1910.1200",   # Hazard communication (chemicals / hazardous waste)
    "1910.132",    # Personal protective equipment
    "1910.141",    # Sanitation / sharps disposal containers
]

OUTPUT_ACUTE      = "acute_prospects.csv"
OUTPUT_NATIONWIDE = "nationwide_prospects.csv"

# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

df = pd.read_csv(INPUT_FILE, dtype={"naics_code": str, "site_state": str})

# ---------------------------------------------------------------------------
# FILTER 1 — Healthcare facilities only (NAICS starting with "62")
# ---------------------------------------------------------------------------

df = df[df["naics_code"].str.startswith(HEALTHCARE_NAICS_PREFIX, na=False)]

# ---------------------------------------------------------------------------
# FILTER 2 — Target violation standards only
# ---------------------------------------------------------------------------
# OSHA stores the standard as a string like "1910.1030" or "1910.1030(d)(2)(i)".
# We match on prefix so subparts are included automatically.

def matches_target(standard_value):
    if pd.isna(standard_value):
        return False
    return any(str(standard_value).startswith(s) for s in TARGET_STANDARDS)

df = df[df["standard"].apply(matches_target)]

# ---------------------------------------------------------------------------
# DERIVED COLUMN — days_since_citation
# ---------------------------------------------------------------------------
# Calculated from issuance_dt to today. Lower = more recent = higher priority.

df["issuance_dt"] = pd.to_datetime(df["issuance_dt"], errors="coerce")
today = pd.Timestamp(date.today())
df["days_since_citation"] = (today - df["issuance_dt"]).dt.days

# Drop rows where issuance_dt couldn't be parsed (no valid date = can't sort)
df = df.dropna(subset=["days_since_citation"])
df["days_since_citation"] = df["days_since_citation"].astype(int)

# ---------------------------------------------------------------------------
# SPLIT — Acute territory (MO + KS) vs. Nationwide (everything else)
# ---------------------------------------------------------------------------

df["site_state"] = df["site_state"].str.upper().str.strip()

acute      = df[df["site_state"].isin(ACUTE_STATES)].copy()
nationwide = df[~df["site_state"].isin(ACUTE_STATES)].copy()

# ---------------------------------------------------------------------------
# SORT — Ascending by days_since_citation (freshest violations first)
# ---------------------------------------------------------------------------

acute      = acute.sort_values("days_since_citation", ascending=True)
nationwide = nationwide.sort_values("days_since_citation", ascending=True)

# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

acute.to_csv(OUTPUT_ACUTE, index=False)
nationwide.to_csv(OUTPUT_NATIONWIDE, index=False)

print(f"acute_prospects.csv      — {len(acute):,} rows  ({', '.join(sorted(ACUTE_STATES))})")
print(f"nationwide_prospects.csv — {len(nationwide):,} rows  (all other states)")
