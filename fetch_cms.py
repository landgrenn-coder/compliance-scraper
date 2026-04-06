"""
fetch_cms.py — Downloads and joins three CMS nursing home datasets.

Datasets pulled:
  1. NH_HealthCitations  — F880/F881 infection-control deficiencies
  2. NH_Penalties        — civil monetary fines per facility
  3. NH_SurveySummary    — most-recent-survey totals per facility

Outputs cms_deficiencies.csv sorted by prospect_score descending.
No API key required.
"""

import io
import sys
from datetime import date, timedelta

import pandas as pd
import requests

# ── Config ────────────────────────────────────────────────────────────────────
CATALOG_URL = (
    "https://data.cms.gov/provider-data/api/1/metastore/schemas/"
    "dataset/items?show-references=true&limit=500"
)
OUTPUT_FILE   = "cms_deficiencies.csv"
TARGET_TAGS   = {"0880", "0814"}
CUTOFF_DATE   = date.today() - timedelta(days=90)
THREE_YR_DATE = date.today() - timedelta(days=3 * 365)
TIMEOUT       = 120
CCN           = "CMS Certification Number (CCN)"

# ── Step 1: Fetch catalog ─────────────────────────────────────────────────────
print("Step 1 — Fetching CMS provider-data catalog...")
catalog = requests.get(CATALOG_URL, timeout=TIMEOUT).json()
print(f"  {len(catalog)} datasets found")

# ── Step 2: Find download URLs for all three files ────────────────────────────
print("Step 2 — Locating target CSV files...")
urls = {}
for ds in catalog:
    for dist in ds.get("distribution", []):
        u = dist.get("downloadURL", "")
        for key in ("NH_HealthCitations", "NH_Penalties", "NH_SurveySummary"):
            if key in u and u.endswith(".csv") and key not in urls:
                urls[key] = u

missing = [k for k in ("NH_HealthCitations", "NH_Penalties", "NH_SurveySummary") if k not in urls]
if missing:
    print(f"  ERROR: could not find URLs for: {missing}")
    sys.exit(1)

for k, u in urls.items():
    print(f"  {k}: {u}")

# ── Step 3: Download helper ───────────────────────────────────────────────────
def download_csv(name, url):
    print(f"  Downloading {name}...")
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    mb = len(resp.content) / 1_048_576
    df = pd.read_csv(io.StringIO(resp.text), dtype=str, low_memory=False)
    print(f"    {mb:.1f} MB — {len(df):,} rows")
    df.columns = df.columns.str.strip()
    return df

print("Step 3 — Downloading CSVs...")
health_df  = download_csv("NH_HealthCitations", urls["NH_HealthCitations"])
penalty_df = download_csv("NH_Penalties",        urls["NH_Penalties"])
survey_df  = download_csv("NH_SurveySummary",    urls["NH_SurveySummary"])

# ── Step 4: Filter health citations ──────────────────────────────────────────
print("Step 4 — Filtering health citations...")
health_df["Deficiency Tag Number"] = health_df["Deficiency Tag Number"].str.strip()
health_df = health_df[health_df["Deficiency Tag Number"].isin(TARGET_TAGS)].copy()
print(f"  After tag filter (F880/F881): {len(health_df):,}")

health_df["Survey Date"] = pd.to_datetime(health_df["Survey Date"], errors="coerce")
health_df = health_df[health_df["Survey Date"].dt.date >= CUTOFF_DATE].copy()
print(f"  After 90-day filter:          {len(health_df):,}")

health_df["days_since_survey"] = (date.today() - health_df["Survey Date"].dt.date).apply(lambda d: d.days)

# ── Step 5: Add severity_priority ────────────────────────────────────────────
print("Step 5 — Adding severity_priority...")
SEVERITY_MAP = {
    **{c: "Critical" for c in "IJKL"},
    **{c: "Serious"  for c in "EFGH"},
    **{c: "Minor"    for c in "ABCD"},
}
health_df["Scope Severity Code"] = health_df["Scope Severity Code"].str.strip()
health_df["severity_priority"]   = health_df["Scope Severity Code"].map(SEVERITY_MAP).fillna("Unknown")

# ── Step 6: Build Penalties summary per CCN ───────────────────────────────────
print("Step 6 — Building penalties summary...")
penalty_df["Fine Amount"]   = pd.to_numeric(penalty_df["Fine Amount"],   errors="coerce")
penalty_df["Penalty Date"]  = pd.to_datetime(penalty_df["Penalty Date"], errors="coerce")
penalty_df["Penalty Type"]  = penalty_df["Penalty Type"].str.strip()

fines = penalty_df[penalty_df["Penalty Type"].str.lower() == "fine"].copy()

# Most recent fine per CCN
recent = (
    fines.sort_values("Penalty Date", ascending=False)
         .drop_duplicates(subset=[CCN])[[CCN, "Fine Amount", "Penalty Date"]]
         .rename(columns={"Fine Amount": "recent_fine_amount", "Penalty Date": "fine_date"})
)

# Sum of fines in last 3 years per CCN
fines_3yr = fines[fines["Penalty Date"].dt.date >= THREE_YR_DATE].copy()
total_3yr  = (
    fines_3yr.groupby(CCN)["Fine Amount"]
              .sum()
              .reset_index()
              .rename(columns={"Fine Amount": "total_fines_3yr"})
)

pen_summary = recent.merge(total_3yr, on=CCN, how="outer")
pen_summary["recent_fine_amount"] = pen_summary["recent_fine_amount"].fillna(0)
pen_summary["total_fines_3yr"]    = pen_summary["total_fines_3yr"].fillna(0)
pen_summary["fine_date"]          = pen_summary["fine_date"].dt.strftime("%Y-%m-%d").fillna("")
print(f"  Facilities with fine history: {len(pen_summary):,}")

# ── Step 7: Build Survey Summary (Cycle 1 only) per CCN ──────────────────────
print("Step 7 — Building survey summary (cycle 1)...")
survey_df["Inspection Cycle"] = survey_df["Inspection Cycle"].str.strip()
cycle1 = survey_df[survey_df["Inspection Cycle"] == "1"][[
    CCN,
    "Health Survey Date",
    "Total Number of Health Deficiencies",
]].copy()

cycle1 = cycle1.rename(columns={
    # "std_survey_date" = date of the annual standard survey (NOT complaint survey date)
    # These may differ from the citation Survey Date, which can come from a complaint survey
    # that occurred later but is still labeled Inspection Cycle 1 by CMS.
    "Health Survey Date":                  "std_survey_date",
    "Total Number of Health Deficiencies": "std_survey_deficiencies",
})
cycle1["std_survey_deficiencies"] = pd.to_numeric(
    cycle1["std_survey_deficiencies"], errors="coerce"
).fillna(0)
print(f"  Facilities with cycle-1 data: {len(cycle1):,}")

# ── Step 8: Join all three datasets ──────────────────────────────────────────
print("Step 8 — Joining datasets on CCN...")
result = health_df.merge(pen_summary, on=CCN, how="left")
result = result.merge(cycle1,         on=CCN, how="left")

result["recent_fine_amount"]       = pd.to_numeric(result["recent_fine_amount"],       errors="coerce").fillna(0)
result["total_fines_3yr"]          = pd.to_numeric(result["total_fines_3yr"],          errors="coerce").fillna(0)
result["std_survey_deficiencies"]   = pd.to_numeric(result["std_survey_deficiencies"],   errors="coerce").fillna(0)
result["fine_date"]                = result["fine_date"].fillna("")
result["std_survey_date"]          = result["std_survey_date"].fillna("")

# ── Step 9: Prospect score ────────────────────────────────────────────────────
print("Step 9 — Calculating prospect_score...")

def score_row(r):
    s = 0
    sev = str(r.get("Scope Severity Code", "")).strip().upper()
    if sev in "EF":  s += 2
    elif sev in "GH": s += 3
    elif sev in "IJKL": s += 5

    if float(r.get("recent_fine_amount", 0) or 0) > 0:
        s += 3

    defic = float(r.get("std_survey_deficiencies", 0) or 0)
    if defic > 20:   s += 3
    elif defic > 10: s += 2

    survey_date = r.get("Survey Date")
    if pd.notna(survey_date):
        days = (date.today() - pd.Timestamp(survey_date).date()).days
        if days <= 30:
            s += 2
    return s

result["prospect_score"] = result.apply(score_row, axis=1)

# ── Step 10: Format and save ──────────────────────────────────────────────────
print("Step 10 — Saving output...")
result["Survey Date"]   = result["Survey Date"].dt.strftime("%Y-%m-%d")
result["Inspection Report"] = (
    "https://www.medicare.gov/care-compare/details/nursing-home/"
    + result[CCN].str.strip()
)

result = result.sort_values("prospect_score", ascending=False).reset_index(drop=True)
result.to_csv(OUTPUT_FILE, index=False)

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 55)
print("  SUMMARY")
print("=" * 55)
print(f"  Total rows:                  {len(result):,}")
print(f"  Rows with fines (recent):    {(result['recent_fine_amount'] > 0).sum():,}")
print(f"  Rows with cycle-1 data:      {(result['std_survey_deficiencies'] > 0).sum():,}")
print(f"  Score distribution:")
for s in sorted(result["prospect_score"].unique(), reverse=True):
    n = (result["prospect_score"] == s).sum()
    print(f"    Score {s:>2}: {n:>3} facilities")
print(f"  Saved to: {OUTPUT_FILE}")
print("=" * 55)
