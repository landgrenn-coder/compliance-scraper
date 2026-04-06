"""
fetch_cms.py — Downloads CMS nursing home health citation data.
Finds the latest NH_HealthCitations CSV dynamically via the CMS data.json catalog.
No API key required.
"""

import io
import sys
from datetime import date, timedelta

import pandas as pd
import requests

CATALOG_URL  = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items?show-references=true&limit=500"
OUTPUT_FILE  = "cms_deficiencies.csv"
TARGET_TAGS  = {"0880", "0881"}   # stored without the "F" prefix in the CSV
CUTOFF_DATE  = date.today() - timedelta(days=90)
TIMEOUT      = 120  # seconds — large file

# ── Step 1: Fetch catalog ─────────────────────────────────────────────────────
print("Step 1 — Fetching CMS provider-data catalog...")
resp = requests.get(CATALOG_URL, timeout=TIMEOUT)
resp.raise_for_status()
catalog = resp.json()
print(f"  Catalog loaded: {len(catalog)} datasets")

# ── Step 2: Find NH_HealthCitations download URL ──────────────────────────────
print("Step 2 — Searching for NH_HealthCitations entry...")
download_url = None

for dataset in catalog:
    for dist in dataset.get("distribution", []):
        url = dist.get("downloadURL", "") or dist.get("accessURL", "")
        if "NH_HealthCitations" in url and url.endswith(".csv"):
            download_url = url
            break
    if download_url:
        break

if not download_url:
    print("ERROR: NH_HealthCitations CSV not found in catalog.")
    sys.exit(1)

print(f"  Found: {download_url}")

# ── Step 3: Download CSV ──────────────────────────────────────────────────────
print("Step 3 — Downloading CSV (may be large)...")
resp = requests.get(download_url, timeout=TIMEOUT)
resp.raise_for_status()
raw_text = resp.text
total_rows = raw_text.count("\n") - 1  # rough line count before parsing
print(f"  Downloaded {len(resp.content) / 1_048_576:.1f} MB")

# ── Step 4: Parse CSV ─────────────────────────────────────────────────────────
print("Step 4 — Parsing CSV...")
df = pd.read_csv(io.StringIO(raw_text), dtype=str, low_memory=False)
print(f"  Total rows downloaded:   {len(df):,}")

# Normalise column names (strip whitespace)
df.columns = df.columns.str.strip()

# ── Step 5: Filter to target deficiency tags ──────────────────────────────────
print("Step 5 — Filtering deficiency tags (F880, F881)...")
tag_col = "Deficiency Tag Number"
df[tag_col] = df[tag_col].str.strip()
df_tagged = df[df[tag_col].isin(TARGET_TAGS)].copy()
print(f"  Rows after tag filter:   {len(df_tagged):,}")

# ── Step 6: Filter to last 90 days ───────────────────────────────────────────
print(f"Step 6 — Filtering Survey Date to last 90 days (since {CUTOFF_DATE})...")
date_col = "Survey Date"
df_tagged[date_col] = pd.to_datetime(df_tagged[date_col], errors="coerce")
df_recent = df_tagged[df_tagged[date_col].dt.date >= CUTOFF_DATE].copy()
print(f"  Rows after 90-day filter:{len(df_recent):,}")

# ── Step 7: Add days_since_survey column ─────────────────────────────────────
today = date.today()
df_recent["days_since_survey"] = (
    today - df_recent[date_col].dt.date
).apply(lambda d: d.days)

# ── Step 8: Save output ───────────────────────────────────────────────────────
print(f"Step 8 — Saving to {OUTPUT_FILE}...")
df_recent.to_csv(OUTPUT_FILE, index=False)

# ── Step 9: Summary ───────────────────────────────────────────────────────────
print()
print("=" * 50)
print("  SUMMARY")
print("=" * 50)
print(f"  Total rows downloaded:   {len(df):,}")
print(f"  After tag filter:        {len(df_tagged):,}")
print(f"  After 90-day filter:     {len(df_recent):,}")
print(f"  Saved to:                {OUTPUT_FILE}")
print("=" * 50)
