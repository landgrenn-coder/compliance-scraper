"""
generate_html.py — Injects current data from all three CSVs into index.html.

Called automatically by run_weekly.sh after update.py completes.
Can also be run manually:  python3 generate_html.py
"""

import json
import os
import re
from datetime import date

import pandas as pd

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OSHA_CSV    = os.path.join(SCRIPT_DIR, "healthcare_violations_final.csv")
CMS_CSV     = os.path.join(SCRIPT_DIR, "cms_deficiencies.csv")
NF_CSV      = os.path.join(SCRIPT_DIR, "new_facilities.csv")
HTML_PATH   = os.path.join(SCRIPT_DIR, "index.html")

print("generate_html.py — injecting data into index.html")

# ── Load all three datasets ────────────────────────────────────────────────
if not os.path.exists(OSHA_CSV):
    print(f"  ERROR: {OSHA_CSV} not found")
    raise SystemExit(1)

osha_df = pd.read_csv(OSHA_CSV, dtype=str)
osha_records = osha_df.fillna("").to_dict("records")
print(f"  OSHA records:         {len(osha_records):,}")

cms_records = []
if os.path.exists(CMS_CSV):
    cms_df = pd.read_csv(CMS_CSV, dtype=str)
    cms_records = cms_df.fillna("").to_dict("records")
    print(f"  CMS records:          {len(cms_records):,}")
else:
    print(f"  WARNING: {CMS_CSV} not found — CMS_DATA will be empty")

nf_records = []
if os.path.exists(NF_CSV):
    nf_df = pd.read_csv(NF_CSV, dtype=str)
    nf_records = nf_df.fillna("").to_dict("records")
    print(f"  New facility records: {len(nf_records):,}")
else:
    print(f"  WARNING: {NF_CSV} not found — NEW_FACILITIES_DATA will be empty")

# ── Read current HTML ──────────────────────────────────────────────────────
with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ── Replace RAW_DATA block ─────────────────────────────────────────────────
osha_json = json.dumps(osha_records, indent=2, ensure_ascii=False)
html, n = re.subn(
    r"const RAW_DATA = \[[\s\S]*?\];",
    f"const RAW_DATA = {osha_json};",
    html, count=1,
)
if n == 0:
    print("  ERROR: RAW_DATA marker not found in index.html")
    raise SystemExit(1)

# ── Replace CMS_DATA block ─────────────────────────────────────────────────
cms_json = json.dumps(cms_records, ensure_ascii=False)
html, n = re.subn(
    r"const CMS_DATA = \[[\s\S]*?\];",
    f"const CMS_DATA = {cms_json};",
    html, count=1,
)
if n == 0:
    print("  ERROR: CMS_DATA marker not found in index.html")
    raise SystemExit(1)

# ── Replace NEW_FACILITIES_DATA block ─────────────────────────────────────
nf_json = json.dumps(nf_records, ensure_ascii=False)
html, n = re.subn(
    r"const NEW_FACILITIES_DATA = \[[\s\S]*?\];",
    f"const NEW_FACILITIES_DATA = {nf_json};",
    html, count=1,
)
if n == 0:
    print("  ERROR: NEW_FACILITIES_DATA marker not found in index.html")
    raise SystemExit(1)

# ── Update tab label counts ────────────────────────────────────────────────
html = re.sub(r"OSHA Violations \(\d+\)", f"OSHA Violations ({len(osha_records)})", html)
html = re.sub(r"CMS Deficiencies \(\d+\)", f"CMS Deficiencies ({len(cms_records)})", html)
html = re.sub(r"New Facilities \(\d+\)", f"New Facilities ({len(nf_records)})", html)

# ── Update the meta line ───────────────────────────────────────────────────
today_str = str(date.today())
html = re.sub(
    r"Data last updated: [\d-]+\s*&nbsp;·&nbsp;\s*[\d,]+ facilities",
    f"Data last updated: {today_str} &nbsp;·&nbsp; {len(osha_records):,} facilities",
    html, count=1,
)

# ── Write updated HTML ─────────────────────────────────────────────────────
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"  index.html updated — OSHA:{len(osha_records)} CMS:{len(cms_records)} NF:{len(nf_records)} — {today_str}")
