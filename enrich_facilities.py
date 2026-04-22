"""
enrich_facilities.py — Adds phone, authorized_official, official_title to new_facilities.csv
by looking up each NPI directly. Much faster than a full re-scrape.
"""
import time
import sys
import pandas as pd
import requests
from datetime import date

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

phones, officials, titles = [], [], []
errors = 0

for i, row in df.iterrows():
    npi = str(row.get("npi", "")).strip()
    if not npi:
        phones.append(""); officials.append(""); titles.append("")
        continue
    try:
        r = requests.get(API_URL, params={"version": "2.1", "number": npi}, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            rec   = results[0]
            basic = rec.get("basic", {})
            addr  = practice_address(rec.get("addresses", []))
            phone = addr.get("telephone_number", "")
            ao_f  = basic.get("authorized_official_first_name", "").strip().title()
            ao_l  = basic.get("authorized_official_last_name",  "").strip().title()
            ao_t  = basic.get("authorized_official_title_or_position", "").strip()
            phones.append(phone)
            officials.append(f"{ao_f} {ao_l}".strip())
            titles.append(ao_t)
        else:
            phones.append(""); officials.append(""); titles.append("")
    except Exception as e:
        errors += 1
        phones.append(""); officials.append(""); titles.append("")

    time.sleep(PAUSE)

    if (i + 1) % 100 == 0:
        pct = (i + 1) / len(df) * 100
        has_phone = sum(1 for p in phones if p)
        print(f"  {i+1:,}/{len(df):,} ({pct:.0f}%) — {has_phone:,} phone numbers found", flush=True)

df["phone"]                = phones
df["authorized_official"]  = officials
df["official_title"]       = titles

# Reorder columns
cols = ["npi","organization_name","practice_address","city","state","zip",
        "phone","authorized_official","official_title",
        "taxonomy_code","taxonomy_description","enumeration_date","days_since_enrollment","data_complete"]
df = df[[c for c in cols if c in df.columns]]

df.to_csv(NF_CSV, index=False)

has_phone   = (df["phone"] != "").sum()
has_contact = (df["authorized_official"] != "").sum()
print(f"\n  Done. Errors: {errors}")
print(f"  Phone numbers found:  {has_phone:,} / {len(df):,}")
print(f"  Contacts found:       {has_contact:,} / {len(df):,}")
print(f"  Saved to: {NF_CSV}")
