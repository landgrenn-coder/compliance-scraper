"""
enrich_facilities.py — Enriches new_facilities.csv with:
  - phone, authorized_official, official_title  (from NPPES per-NPI lookup)
  - organizational_subpart, parent_org           (from NPPES — YES/NO + parent name)
  - group_indicator                              (derived: Standalone / Part of Group / Group N locations)
"""
import time
import pandas as pd
import requests
from datetime import date
from collections import Counter

SCRIPT_DIR = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
NF_CSV     = __import__("os").path.join(SCRIPT_DIR, "new_facilities.csv")
API_URL    = "https://npiregistry.cms.hhs.gov/api/"
PAUSE      = 0.2
TIMEOUT    = 20

print(f"enrich_facilities.py — {date.today()}")
df = pd.read_csv(NF_CSV, dtype=str)
print(f"  Loaded {len(df):,} records")

def practice_address(addresses):
    for a in addresses:
        if a.get("address_purpose") == "LOCATION":
            return a
    return addresses[0] if addresses else {}

phones, officials, titles, subparts, parents = [], [], [], [], []
errors = 0

for i, row in df.iterrows():
    npi = str(row.get("npi", "")).strip()
    if not npi:
        phones.append(""); officials.append(""); titles.append("")
        subparts.append(""); parents.append("")
        continue
    try:
        r = requests.get(API_URL, params={"version": "2.1", "number": npi}, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            rec    = results[0]
            basic  = rec.get("basic", {})
            addr   = practice_address(rec.get("addresses", []))
            ao_f   = basic.get("authorized_official_first_name", "").strip().title()
            ao_l   = basic.get("authorized_official_last_name",  "").strip().title()
            phones.append(addr.get("telephone_number", ""))
            officials.append(f"{ao_f} {ao_l}".strip())
            titles.append(basic.get("authorized_official_title_or_position", "").strip())
            subparts.append(basic.get("organizational_subpart", "").strip().upper())
            parents.append(basic.get("parent_organization_legal_business_name", "").strip().title())
        else:
            phones.append(""); officials.append(""); titles.append("")
            subparts.append(""); parents.append("")
    except Exception:
        errors += 1
        phones.append(""); officials.append(""); titles.append("")
        subparts.append(""); parents.append("")

    time.sleep(PAUSE)

    if (i + 1) % 100 == 0:
        pct = (i + 1) / len(df) * 100
        print(f"  {i+1:,}/{len(df):,} ({pct:.0f}%) — {sum(1 for p in phones if p):,} phones, "
              f"{sum(1 for s in subparts if s=='YES'):,} subparts", flush=True)

df["phone"]               = phones
df["authorized_official"] = officials
df["official_title"]      = titles
df["organizational_subpart"]  = subparts
df["parent_org"]          = parents

# ── Within-dataset group detection ────────────────────────────────────────────
# Count how many records share the same authorized official (non-empty).
# Same official across multiple NPIs = same owner operating multiple locations.
official_counts = Counter(o for o in df["authorized_official"] if o.strip())

def group_indicator(row):
    subpart    = str(row.get("organizational_subpart", "")).strip().upper()
    parent     = str(row.get("parent_org", "")).strip()
    official   = str(row.get("authorized_official", "")).strip()
    org_name   = str(row.get("organization_name", "")).strip()

    # 1. NPPES explicitly says it's a subpart and names the parent
    if subpart == "YES" and parent and parent.lower() != org_name.lower():
        return f"Part of group: {parent}"

    # 2. NPPES says subpart but no parent name captured
    if subpart == "YES":
        return "Part of group"

    # 3. Same authorized official runs multiple locations in our dataset
    if official and official_counts[official] > 1:
        n = official_counts[official]
        return f"Group — {n} locations (same owner)"

    return "Standalone"

df["group_indicator"] = df.apply(group_indicator, axis=1)

# ── Reorder and save ───────────────────────────────────────────────────────────
cols = [
    "npi", "organization_name", "practice_address", "city", "state", "zip",
    "phone", "authorized_official", "official_title",
    "organizational_subpart", "parent_org", "group_indicator",
    "taxonomy_code", "taxonomy_description",
    "enumeration_date", "days_since_enrollment", "data_complete",
]
df = df[[c for c in cols if c in df.columns]]
df.to_csv(NF_CSV, index=False)

n_standalone = (df["group_indicator"] == "Standalone").sum()
n_subpart    = df["group_indicator"].str.startswith("Part of group").sum()
n_grouped    = df["group_indicator"].str.startswith("Group —").sum()

print(f"\n  Done. API errors: {errors}")
print(f"  Phone numbers:  {(df['phone'] != '').sum():,} / {len(df):,}")
print(f"  Standalone:     {n_standalone:,}")
print(f"  Part of group:  {n_subpart:,}")
print(f"  Same-owner grp: {n_grouped:,}")
print(f"  Saved to: {NF_CSV}")
