"""
fetch_osha.py  —  Option 2 implementation

Strategy: violations first (small, tightly filtered), then one targeted
inspection lookup per unique activity_nr. Far fewer API calls than pulling
all-time healthcare inspections.

HOW TO RUN:
    python3 fetch_osha.py           # full run
    python3 fetch_osha.py --test    # 3-violation sample to verify data shape

REQUIRES:
    config.py with API_KEY defined

OUTPUTS:
    violations_raw.csv          all 2026 BBP/HazWaste violations
    inspections_raw.csv         one inspection record per unique activity_nr
    healthcare_violations.csv   final joined + filtered prospect list

⚠️  FLAGS:

FLAG 1 — standard field format
    The API stores CFR standard codes in compact numeric format, no period.
    CFR 1910.1030 (bloodborne pathogens)  → "19101030..."
    CFR 1910.1200 (hazard communication)  → "19101200..."

FLAG 2 — NAICS filter is applied locally after the join
    Violations are not filtered by NAICS server-side. Some activity_nrs
    will belong to non-healthcare facilities. The NAICS 62% filter in
    Step 5 handles this.

FLAG 3 — issuance_date year filter is coarse
    LIKE '2026%' is used server-side because the API does not support
    greater_than on date fields. A precise 90-day cutoff is applied
    locally in Step 6.

FLAG 4 — Per-activity_nr lookup volume
    Each unique activity_nr = one API call. With 15s pauses, 400 lookups
    = ~100 minutes. Run overnight if the violation count is high.
    Check violations_raw.csv row count after Step 1 to estimate.
"""

import json
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests

from config import API_KEY

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

INSPECTION_URL = "https://apiprod.dol.gov/v4/get/OSHA/inspection/json"
VIOLATION_URL  = "https://apiprod.dol.gov/v4/get/OSHA/violation/json"

PAGE_SIZE              = 200
PAUSE_BETWEEN_REQUESTS = 30.0   # seconds — 30s avoids API 429 rate limits reliably
RETRY_BACKOFF_BASE     = 60     # seconds for first retry on 429/502/503
MAX_RETRIES            = 5

YEAR_PREFIX  = str(date.today().year)           # "2026"
CUTOFF_DATE  = date.today() - timedelta(days=90)

VIOLATION_FILTER = json.dumps({
    "and": [
        {"or": [
            {"field": "standard",      "operator": "like", "value": "19101030%"},
            {"field": "standard",      "operator": "like", "value": "19101200%"},
        ]},
        {"field": "issuance_date", "operator": "like", "value": f"{YEAR_PREFIX}%"},
    ]
})

VIOLATIONS_RAW_FILE   = "violations_raw.csv"
INSPECTIONS_RAW_FILE  = "inspections_raw.csv"
OUTPUT_FILE           = "healthcare_violations.csv"

# --test flag: pull only 3 violations and their inspections, print and exit
TEST_MODE = "--test" in sys.argv
GO_MODE   = "--go"   in sys.argv

# ---------------------------------------------------------------------------
# HELPER — single request with retry on transient errors
# ---------------------------------------------------------------------------

def fetch_with_retry(url, params):
    """
    GET request with exponential backoff on connection errors AND bad status codes.
    Retries on: TCP timeouts, connection resets, 429, 500, 502, 503, 504.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=60)
        except requests.exceptions.RequestException as e:
            wait = RETRY_BACKOFF_BASE * (2 ** attempt)
            print(f"  Connection error ({type(e).__name__}) — waiting {wait}s "
                  f"before retry {attempt + 1}/{MAX_RETRIES}...")
            time.sleep(wait)
            continue
        if response.status_code in (429, 500, 502, 503, 504):
            wait = RETRY_BACKOFF_BASE * (2 ** attempt)
            print(f"  HTTP {response.status_code} — waiting {wait}s "
                  f"before retry {attempt + 1}/{MAX_RETRIES}...")
            time.sleep(wait)
        else:
            break
    else:
        raise RuntimeError(
            f"Still failing after {MAX_RETRIES} retries. "
            f"Try increasing RETRY_BACKOFF_BASE (currently {RETRY_BACKOFF_BASE}s)."
        )
    # 401/403 = bad API key | 400 = bad filter syntax
    response.raise_for_status()
    return response

# ---------------------------------------------------------------------------
# HELPER — extract rows from API response (handles list or dict wrapper)
# ---------------------------------------------------------------------------

def extract_rows(response):
    # Empty body (204 or empty 200 after last page) means no more records
    if not response.text.strip():
        return []
    data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return next((v for v in data.values() if isinstance(v, list)), [])
    return []

# ---------------------------------------------------------------------------
# STEP 1 — Pull all 2026 BBP/HazWaste violations
# ---------------------------------------------------------------------------

VIOLATIONS_CHECKPOINT = "violations_checkpoint.csv"

print("=" * 60)
print(f"STEP 1 — Fetching violations  "
      f"({'TEST MODE: limit 3' if TEST_MODE else f'year={YEAR_PREFIX}, paginating'})")
print("=" * 60)

# If the completed output file already exists, skip the API pull entirely
if os.path.exists(VIOLATIONS_RAW_FILE) and not TEST_MODE:
    print(f"  {VIOLATIONS_RAW_FILE} already exists — skipping API pull.")
    all_violations = pd.read_csv(VIOLATIONS_RAW_FILE, dtype=str).to_dict("records")
    offset = len(all_violations)
    skip_violation_fetch = True
# Otherwise resume from checkpoint if available
elif os.path.exists(VIOLATIONS_CHECKPOINT) and not TEST_MODE:
    _ckpt = pd.read_csv(VIOLATIONS_CHECKPOINT, dtype=str)
    all_violations = _ckpt.to_dict("records")
    offset = len(all_violations)
    skip_violation_fetch = False
    print(f"  Resuming from checkpoint — {len(all_violations):,} rows already fetched.")
else:
    all_violations = []
    offset = 0
    skip_violation_fetch = False

page   = (offset // PAGE_SIZE) + 1
limit  = 3 if TEST_MODE else PAGE_SIZE

while not skip_violation_fetch:
    params = {
        "X-API-KEY":     API_KEY,
        "limit":         limit,
        "offset":        offset,
        "filter_object": VIOLATION_FILTER,
    }
    response = fetch_with_retry(VIOLATION_URL, params)
    rows = extract_rows(response)

    if not rows:
        print(f"  Done. {len(all_violations):,} violation records fetched.")
        break

    all_violations.extend(rows)
    print(f"  Page {page:>3} | offset {offset:>6,} | "
          f"+{len(rows)} rows | total: {len(all_violations):,}")

    # In test mode stop after the first (and only) page of 3
    if TEST_MODE:
        print("  [TEST MODE] Stopping after first page.")
        break

    # Save checkpoint after every page so a crash is recoverable
    pd.DataFrame(all_violations).to_csv(VIOLATIONS_CHECKPOINT, index=False)

    offset += PAGE_SIZE
    page   += 1
    time.sleep(PAUSE_BETWEEN_REQUESTS)

violations_df = pd.DataFrame(all_violations)
violations_df.to_csv(VIOLATIONS_RAW_FILE, index=False)
# Clean up checkpoint now that the full pull is complete
if os.path.exists(VIOLATIONS_CHECKPOINT):
    os.remove(VIOLATIONS_CHECKPOINT)
print(f"  Saved to {VIOLATIONS_RAW_FILE}")

# ---------------------------------------------------------------------------
# STEP 2 — Apply 45-day filter, then extract unique activity_nr values
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print(f"STEP 2 — Filtering to last 90 days and extracting activity_nrs")
print("=" * 60)

violations_df["issuance_date"] = pd.to_datetime(
    violations_df["issuance_date"], errors="coerce"
)
violations_filtered_df = violations_df[
    violations_df["issuance_date"] >= pd.Timestamp(CUTOFF_DATE)
].copy()

unique_activity_nrs = violations_filtered_df["activity_nr"].dropna().unique().tolist()
print(f"  Violations fetched (all):    {len(violations_df):,}")
print(f"  After 45-day filter:         {len(violations_filtered_df):,}")
print(f"  Unique activity_nrs:         {len(unique_activity_nrs):,}")

# ---------------------------------------------------------------------------
# STEP 2b — Confirm before starting inspection lookups
# ---------------------------------------------------------------------------

estimated_seconds = len(unique_activity_nrs) * PAUSE_BETWEEN_REQUESTS
estimated_minutes = estimated_seconds / 60
estimated_hours   = estimated_minutes / 60

print()
print("=" * 60)
print("STEP 2b — Ready to start inspection lookups")
print("=" * 60)
print(f"  Unique activity_nrs found:   {len(unique_activity_nrs):,}")
print(f"  Pause between requests:      {PAUSE_BETWEEN_REQUESTS}s")
print(f"  Estimated runtime:           "
      f"{estimated_minutes:.0f} min ({estimated_hours:.1f} hrs)")
print()

if not TEST_MODE and not GO_MODE:
    print("  Run with --go to start inspection lookups:")
    print("  python3 fetch_osha.py --go")
    sys.exit(0)

# ---------------------------------------------------------------------------
# STEP 3 — Fetch one inspection record per unique activity_nr
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print(f"STEP 3 — Fetching inspection records "
      f"({len(unique_activity_nrs)} lookups × {PAUSE_BETWEEN_REQUESTS}s pause)")
print("=" * 60)

# Resume support: load already-fetched activity_nrs from inspections_raw.csv
if os.path.exists(INSPECTIONS_RAW_FILE) and not TEST_MODE:
    existing_inspections_df = pd.read_csv(INSPECTIONS_RAW_FILE, dtype=str)
    fetched_nrs = set(existing_inspections_df["activity_nr"].astype(str).tolist())
    all_inspections = existing_inspections_df.to_dict("records")
    print(f"  Resuming — {len(fetched_nrs):,} already fetched from {INSPECTIONS_RAW_FILE}")
else:
    fetched_nrs      = set()
    all_inspections  = []

remaining = [nr for nr in unique_activity_nrs if str(nr) not in fetched_nrs]
print(f"  Remaining lookups:           {len(remaining):,}")

for i, activity_nr in enumerate(remaining, start=1):
    params = {
        "X-API-KEY":     API_KEY,
        "limit":         1,
        "offset":        0,
        "filter_object": json.dumps({
            "field":    "activity_nr",
            "operator": "eq",
            "value":    str(activity_nr),
        }),
    }
    response = fetch_with_retry(INSPECTION_URL, params)
    rows = extract_rows(response)

    if rows:
        all_inspections.extend(rows)
        rec = rows[0]
        print(f"  [{i:>4}/{len(remaining)}] activity_nr={activity_nr} | "
              f"{rec.get('estab_name','?')[:35]:<35} | "
              f"{rec.get('site_city','?')}, {rec.get('site_state','?')} | "
              f"NAICS {rec.get('naics_code','?')}")
    else:
        print(f"  [{i:>4}/{len(remaining)}] activity_nr={activity_nr} | "
              f"(no inspection record found)")

    # Save checkpoint after every lookup so crashes are recoverable
    if not TEST_MODE:
        pd.DataFrame(all_inspections).to_csv(INSPECTIONS_RAW_FILE, index=False)

    # Skip pause after the last request
    if i < len(remaining):
        time.sleep(PAUSE_BETWEEN_REQUESTS)

inspections_df = pd.DataFrame(all_inspections)
if TEST_MODE:
    inspections_df.to_csv(INSPECTIONS_RAW_FILE, index=False)
print(f"  Saved to {INSPECTIONS_RAW_FILE}")

# ---------------------------------------------------------------------------
# STEP 4 — Join violations to inspections on activity_nr
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("STEP 4 — Joining on activity_nr")
print("=" * 60)

violations_df["activity_nr"]  = violations_df["activity_nr"].astype(str)
inspections_df["activity_nr"] = inspections_df["activity_nr"].astype(str)

joined_df = pd.merge(
    violations_df,
    inspections_df,
    on="activity_nr",
    how="inner",
    suffixes=("_violation", "_inspection"),
)
print(f"  Rows after join:             {len(joined_df):,}")

# ---------------------------------------------------------------------------
# STEP 5 — Filter to healthcare facilities (NAICS starting with "62")
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("STEP 5 — Filtering to NAICS 62% (healthcare)")
print("=" * 60)

joined_df["naics_code"] = joined_df["naics_code"].astype(str)
healthcare_df = joined_df[
    joined_df["naics_code"].str.startswith("62", na=False)
].copy()
print(f"  Rows after NAICS 62% filter: {len(healthcare_df):,}")

# ---------------------------------------------------------------------------
# STEP 6 — Local 90-day filter on issuance_date
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print(f"STEP 6 — Filtering to last 90 days (>= {CUTOFF_DATE})")  # now matches CUTOFF_DATE
print("=" * 60)

healthcare_df["issuance_date"] = pd.to_datetime(
    healthcare_df["issuance_date"], errors="coerce"
)
unparseable = healthcare_df["issuance_date"].isna().sum()
if unparseable:
    print(f"  Warning: {unparseable} rows dropped — issuance_date unparseable")

healthcare_df = healthcare_df.dropna(subset=["issuance_date"])
healthcare_df = healthcare_df[
    healthcare_df["issuance_date"] >= pd.Timestamp(CUTOFF_DATE)
].copy()
print(f"  Rows after 90-day filter:    {len(healthcare_df):,}")

# ---------------------------------------------------------------------------
# STEP 7 — Add days_since_citation column
# ---------------------------------------------------------------------------

today = pd.Timestamp(date.today())
healthcare_df["days_since_citation"] = (
    today - healthcare_df["issuance_date"]
).dt.days.astype(int)

# ---------------------------------------------------------------------------
# STEP 8 — Sort ascending by days_since_citation (freshest first)
# ---------------------------------------------------------------------------

healthcare_df = healthcare_df.sort_values(
    "days_since_citation", ascending=True
).reset_index(drop=True)

# ---------------------------------------------------------------------------
# STEP 9 — Save output
# ---------------------------------------------------------------------------

healthcare_df.to_csv(OUTPUT_FILE, index=False)

# ---------------------------------------------------------------------------
# STEP 10 — Summary
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Violations fetched:            {len(violations_df):>8,}")
print(f"Unique inspections looked up:  {len(unique_activity_nrs):>8,}")
print(f"Rows after join:               {len(joined_df):>8,}")
print(f"Rows after NAICS 62% filter:   {len(healthcare_df[healthcare_df['naics_code'].str.startswith('62', na=False)]) if 'naics_code' in healthcare_df.columns else len(healthcare_df):>8,}")
print(f"Rows after 90-day filter:      {len(healthcare_df):>8,}")
print(f"Output saved to:               {OUTPUT_FILE}")
print("=" * 60)

# ---------------------------------------------------------------------------
# TEST MODE — print joined sample and exit
# ---------------------------------------------------------------------------

if TEST_MODE:
    print()
    print("=" * 60)
    print("TEST MODE — Joined sample output")
    print("=" * 60)
    cols = [
        "activity_nr", "estab_name", "site_address", "site_city",
        "site_state", "naics_code", "standard", "issuance_date",
        "current_penalty", "days_since_citation",
    ]
    display_cols = [c for c in cols if c in healthcare_df.columns]
    if healthcare_df.empty:
        print("  No healthcare records in this 3-record sample — try a larger test.")
        print()
        print("  Full joined output (pre-NAICS filter):")
        print(joined_df[[c for c in cols if c in joined_df.columns]].to_string(index=False))
    else:
        print(healthcare_df[display_cols].to_string(index=False))
