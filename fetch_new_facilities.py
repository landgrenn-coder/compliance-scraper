"""
fetch_new_facilities.py — Finds newly enrolled healthcare organizations via NPPES.

Pagination strategy:
  1. Query state × taxonomy_group. The API caps at 1,200 records per query.
  2. If a state+taxonomy combo hits the cap (exactly 1,200 returned), extract
     all unique cities from those results and re-query city-by-city to get
     complete coverage. Records already captured are deduplicated by NPI.
  3. If a city-level query also hits 1,200, it is flagged as Partial.

data_complete column:
  "Yes"               — full result set captured
  "Partial"           — city-level query also hit the API cap; some records missed

No API key required.
"""

import time
import sys
from datetime import date, timedelta

import pandas as pd
import requests

# ── Config ────────────────────────────────────────────────────────────────────
API_URL     = "https://npiregistry.cms.hhs.gov/api/"
OUTPUT_FILE = "new_facilities.csv"
CUTOFF_DATE = date.today() - timedelta(days=90)
API_CAP     = 1200   # NPPES hard cap per query (6 pages × 200)
PAUSE       = 0.25   # seconds between calls
TIMEOUT     = 30

# ── Taxonomy groups ───────────────────────────────────────────────────────────
TAXONOMY_GROUPS = [
    ("Hospital", {
        "282N00000X":  "General Acute Care Hospital",
        "282NW0100X":  "General Acute Care Hospital — Women's",
    }),
    ("Skilled Nursing", {
        "314000000X":  "Skilled Nursing Facility",
        "315D00000X":  "Hospice — Inpatient",
        "315P00000X":  "Intermediate Care Facility",
    }),
    ("Assisted Living", {
        "310400000X":  "Assisted Living Facility",
    }),
    ("Home Health", {
        "251G00000X":  "Home Health — Supports",
        "251E00000X":  "Home Health",
    }),
    ("Ambulatory Surgical", {
        "261QA1903X":  "Ambulatory Surgery Center",
    }),
    ("End-Stage Renal", {
        "261QE0700X":  "Dialysis / ESRD Treatment Facility",
    }),
    ("Clinical Medical Laboratory", {
        "291U00000X":  "Clinical Medical Laboratory",
    }),
    ("Urgent Care", {
        "261QU0200X":  "Urgent Care Center",
    }),
    ("Outpatient", {
        "261QP2300X":  "Outpatient Clinic",
    }),
]

TARGET_CODES = {code for _, grp in TAXONOMY_GROUPS for code in grp}
CODE_LABELS  = {code: label for _, grp in TAXONOMY_GROUPS for code, label in grp.items()}

US_STATES = [
    "AK","AL","AR","AZ","CA","CO","CT","DC","DE","FL","GA","HI","IA","ID",
    "IL","IN","KS","KY","LA","MA","MD","ME","MI","MN","MO","MS","MT","NC",
    "ND","NE","NH","NJ","NM","NV","NY","OH","OK","OR","PA","PR","RI","SC",
    "SD","TN","TX","UT","VA","VT","WA","WI","WV","WY",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def primary_taxonomy(taxonomies):
    for t in taxonomies:
        if t.get("primary"):
            return t.get("code", ""), t.get("desc", "")
    if taxonomies:
        return taxonomies[0].get("code", ""), taxonomies[0].get("desc", "")
    return "", ""


def practice_address(addresses):
    for a in addresses:
        if a.get("address_purpose") == "LOCATION":
            return a
    return addresses[0] if addresses else {}


def extract_record(rec, data_complete="Yes"):
    basic    = rec.get("basic", {})
    tax_code, tax_desc = primary_taxonomy(rec.get("taxonomies", []))
    addr     = practice_address(rec.get("addresses", []))
    enum_str = basic.get("enumeration_date", "")
    try:
        days_ago = (date.today() - date.fromisoformat(enum_str)).days
    except (ValueError, TypeError):
        days_ago = None
    # Authorized official (primary contact for the organization)
    ao_first = basic.get("authorized_official_first_name", "").strip().title()
    ao_last  = basic.get("authorized_official_last_name",  "").strip().title()
    ao_title = basic.get("authorized_official_title_or_position", "").strip()
    ao_name  = f"{ao_first} {ao_last}".strip()
    return {
        "npi":                    rec.get("number", ""),
        "organization_name":      basic.get("organization_name", ""),
        "practice_address":       addr.get("address_1", ""),
        "city":                   addr.get("city", ""),
        "state":                  addr.get("state", ""),
        "zip":                    addr.get("postal_code", "")[:5],
        "phone":                  addr.get("telephone_number", ""),
        "authorized_official":    ao_name,
        "official_title":         ao_title,
        "organizational_subpart": basic.get("organizational_subpart", "").strip().upper(),
        "parent_org":             basic.get("parent_organization_legal_business_name", "").strip().title(),
        "group_indicator":        "",   # computed by enrich_facilities.py
        "taxonomy_code":          tax_code,
        "taxonomy_description":   CODE_LABELS.get(tax_code, tax_desc),
        "enumeration_date":       enum_str,
        "days_since_enrollment":  days_ago,
        "data_complete":          data_complete,
    }


def is_new_enough(rec):
    """Return True if the record's enumeration_date is within the 90-day window."""
    enum_str = rec.get("basic", {}).get("enumeration_date", "")
    try:
        return date.fromisoformat(enum_str) >= CUTOFF_DATE
    except (ValueError, TypeError):
        return False


def matches_code(rec, code_map):
    tax_code, _ = primary_taxonomy(rec.get("taxonomies", []))
    return tax_code in code_map


def api_get(search_term, state, skip, city=None):
    """Single NPPES API call. Returns (results_list, api_calls_made)."""
    params = {
        "version":              "2.1",
        "enumeration_type":     "NPI-2",
        "taxonomy_description": search_term,
        "state":                state,
        "limit":                200,
        "skip":                 skip,
    }
    if city:
        params["city"] = city
    try:
        r = requests.get(API_URL, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("results", []), 1
    except Exception as e:
        label = f"state={state}" + (f", city={city}" if city else "")
        print(f"    WARNING: API error ({label}, skip={skip}): {e}")
        return [], 1


def paginate(search_term, state, code_map, city=None):
    """
    Paginate one state (or state+city) query completely.
    Returns:
        all_raw     — all raw API records returned (regardless of date/code filter)
        hit_cap     — True if we hit the 1200-record API cap
        api_calls   — number of API calls made
    """
    all_raw   = []
    api_calls = 0
    skip      = 0

    while True:
        results, n = api_get(search_term, state, skip, city=city)
        api_calls += n
        time.sleep(PAUSE)

        all_raw.extend(results)

        if len(results) < 200:
            break   # partial page = end of results
        skip += 200
        if skip >= API_CAP:
            break   # hit the cap

    hit_cap = len(all_raw) >= API_CAP
    return all_raw, hit_cap, api_calls


def extract_cities(raw_records):
    """Pull unique city names from a set of raw API records."""
    cities = set()
    for rec in raw_records:
        addr = practice_address(rec.get("addresses", []))
        c = addr.get("city", "").strip()
        if c:
            cities.add(c)
    return sorted(cities)


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 62)
print(f"fetch_new_facilities.py — {date.today()}")
print(f"90-day cutoff: {CUTOFF_DATE}")
print("=" * 62)

# seen_npis tracks all NPIs collected so we can deduplicate on the fly
seen_npis  = {}    # npi → record dict
api_calls  = 0
total_scanned = 0

for search_term, code_map in TAXONOMY_GROUPS:
    print(f"\nTaxonomy: '{search_term}' ({len(code_map)} codes)")
    group_found = 0

    for state in US_STATES:

        # ── Pass 1: full state query ──────────────────────────────────────────
        raw, hit_cap, calls = paginate(search_term, state, code_map)
        api_calls     += calls
        total_scanned += len(raw)

        if not hit_cap:
            # Complete — process all records as data_complete = "Yes"
            for rec in raw:
                if matches_code(rec, code_map) and is_new_enough(rec):
                    r = extract_record(rec, data_complete="Yes")
                    if r["npi"] not in seen_npis:
                        seen_npis[r["npi"]] = r
                        group_found += 1
            continue

        # ── Pass 2: cap hit — re-query city-by-city ───────────────────────────
        # First, collect the records we already have from pass 1 (mark tentatively)
        # We'll refine completeness flags after city pass.
        pass1_npis = set()
        for rec in raw:
            if matches_code(rec, code_map) and is_new_enough(rec):
                r = extract_record(rec, data_complete="Yes")   # tentative
                pass1_npis.add(r["npi"])
                if r["npi"] not in seen_npis:
                    seen_npis[r["npi"]] = r
                    group_found += 1

        cities = extract_cities(raw)
        print(f"    [{state}] cap hit — re-querying {len(cities)} cities")
        any_city_capped = False

        for city in cities:
            city_raw, city_cap, city_calls = paginate(search_term, state, code_map, city=city)
            api_calls     += city_calls
            total_scanned += len(city_raw)

            completeness = "Partial" if city_cap else "Yes"
            if city_cap:
                any_city_capped = True
                print(f"      [{state}/{city}] still capped — marked Partial")

            for rec in city_raw:
                if matches_code(rec, code_map) and is_new_enough(rec):
                    r = extract_record(rec, data_complete=completeness)
                    npi = r["npi"]
                    if npi not in seen_npis:
                        seen_npis[npi] = r
                        group_found += 1
                    else:
                        # Upgrade to Partial if city was capped
                        if completeness == "Partial":
                            seen_npis[npi]["data_complete"] = "Partial"

    print(f"  → {group_found} new facilities")

# ── Build dataframe ───────────────────────────────────────────────────────────
df = pd.DataFrame(list(seen_npis.values()))
if df.empty:
    print("\nNo new facilities found.")
    pd.DataFrame().to_csv(OUTPUT_FILE, index=False)
    sys.exit(0)

df = df.sort_values("enumeration_date", ascending=False).reset_index(drop=True)
df.to_csv(OUTPUT_FILE, index=False)

# ── Summary ───────────────────────────────────────────────────────────────────
n_yes     = (df["data_complete"] == "Yes").sum()
n_partial = (df["data_complete"] == "Partial").sum()

print()
print("=" * 62)
print("  SUMMARY")
print("=" * 62)
print(f"  Total records scanned:    {total_scanned:,}")
print(f"  API calls made:           {api_calls:,}")
print(f"  New facilities found:     {len(df):,}")
print(f"    Complete (data_complete=Yes):     {n_yes:,}")
print(f"    Partial  (data_complete=Partial): {n_partial:,}")
print()
print("  Breakdown by taxonomy:")
for tax, count in df["taxonomy_description"].value_counts().items():
    print(f"    {count:>4}  {tax}")
print()
print(f"  Saved to: {OUTPUT_FILE}")
print("=" * 62)
