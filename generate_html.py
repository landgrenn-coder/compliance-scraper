"""
generate_html.py — Injects current data from healthcare_violations_final.csv into index.html.

Called automatically by run_weekly.sh after update.py completes.
Can also be run manually:  python3 generate_html.py
"""

import json
import os
import re
from datetime import date

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(SCRIPT_DIR, "healthcare_violations_final.csv")
HTML_PATH  = os.path.join(SCRIPT_DIR, "index.html")

print("generate_html.py — injecting data into index.html")

if not os.path.exists(CSV_PATH):
    print(f"  ERROR: {CSV_PATH} not found — skipping HTML generation")
    raise SystemExit(1)

# Load CSV and convert to list of dicts
df = pd.read_csv(CSV_PATH, dtype=str)
records = df.fillna("").to_dict("records")
print(f"  Records loaded: {len(records):,}")

# Serialize to compact JSON (one object per line keeps the diff readable in git)
json_data = json.dumps(records, indent=2, ensure_ascii=False)

# Read current HTML
with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ── Replace RAW_DATA block ──
# Matches: const RAW_DATA = [...any content...];
new_block = f"const RAW_DATA = {json_data};"
html, n_subs = re.subn(
    r"const RAW_DATA = \[[\s\S]*?\];",
    new_block,
    html,
    count=1,
)
if n_subs == 0:
    print("  ERROR: could not find RAW_DATA marker in index.html")
    raise SystemExit(1)

# ── Update the meta line ──
# Matches: "Data last updated: YYYY-MM-DD &nbsp;·&nbsp; N facilities"
today_str = str(date.today())
n = len(records)
html = re.sub(
    r"Data last updated: [\d-]+\s*&nbsp;·&nbsp;\s*\d+ facilities",
    f"Data last updated: {today_str} &nbsp;·&nbsp; {n} facilities",
    html,
    count=1,
)

# Write updated HTML
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"  index.html updated — {n} facilities, as of {today_str}")
