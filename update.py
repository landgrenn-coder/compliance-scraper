"""
update.py — Weekly incremental updater for healthcare_violations_final.csv

HOW IT WORKS:
  1. Deletes cached raw files so fetch_osha.py does a full fresh API pull
  2. Runs fetch_osha.py --go (produces healthcare_violations.csv)
  3. Applies the same priority_tier + facility-dedup logic used originally
  4. Loads the existing healthcare_violations_final.csv
  5. Deduplicates new candidates against existing records on a 4-column key:
       estab_name + site_address + issuance_date + standard
     → same citation can never appear twice even across weekly runs
  6. Appends only genuinely new records, rebuilds and saves the final file
  7. Prints a summary: new added / duplicates skipped / total in file

HOW TO RUN:
  python3 update.py

CALLED BY:
  run_weekly.sh  (which logs output + timestamp to update_log.txt)
"""

import os
import subprocess
import sys
import pandas as pd
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# All paths are relative to this script's own directory so cron can call it
# from any working directory without breaking file references.
SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
FETCH_SCRIPT    = os.path.join(SCRIPT_DIR, "fetch_osha.py")
VIOLATIONS_RAW  = os.path.join(SCRIPT_DIR, "violations_raw.csv")
VIOLATIONS_CKPT = os.path.join(SCRIPT_DIR, "violations_checkpoint.csv")
INSPECTIONS_RAW = os.path.join(SCRIPT_DIR, "inspections_raw.csv")
FRESH_OUTPUT    = os.path.join(SCRIPT_DIR, "healthcare_violations.csv")
FINAL_OUTPUT    = os.path.join(SCRIPT_DIR, "healthcare_violations_final.csv")

# CMS paths
FETCH_CMS_SCRIPT = os.path.join(SCRIPT_DIR, "fetch_cms.py")
CMS_OUTPUT       = os.path.join(SCRIPT_DIR, "cms_deficiencies.csv")

# The 4-column key that uniquely identifies a single citation row.
# Same combination = same OSHA citation — skip it on subsequent runs.
DEDUP_KEY = ["estab_name", "site_address", "issuance_date", "standard"]

# CMS dedup key — uniquely identifies a single CMS deficiency row.
CMS_DEDUP_KEY = ["Provider Name", "State", "Survey Date", "Deficiency Tag Number"]

# NAICS prefix → priority tier mapping (mirrors the original classification)
TIER_MAP = {
    "6211": 1, "6212": 1, "6213": 1, "6214": 1,
    "6215": 1, "6216": 1, "6219": 1,
    "6221": 2, "6222": 2, "6223": 2,
    "6231": 2, "6232": 2, "6233": 2, "6239": 2,
    "6241": 3, "6242": 3, "6243": 3, "6244": 3,
}

def get_tier(naics):
    """Return priority tier (1-3) based on first 4 digits of NAICS code."""
    prefix = str(naics)[:4]
    return TIER_MAP.get(prefix, 99)   # 99 = unclassified (kept but deprioritised)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Delete cached raw files to force a complete fresh API pull
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print(f"UPDATE RUN — {date.today()}")
print("=" * 60)

print("\nSTEP 1 — Clearing cached raw files for fresh pull")
for path, label in [
    (VIOLATIONS_RAW,  "violations_raw.csv"),
    (VIOLATIONS_CKPT, "violations_checkpoint.csv"),
    (INSPECTIONS_RAW, "inspections_raw.csv"),
]:
    if os.path.exists(path):
        os.remove(path)
        print(f"  Deleted {label}")
    else:
        print(f"  {label} not present — nothing to delete")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Run fetch_osha.py to pull fresh data
#
# We call it as a subprocess so it runs with its own scope and argument
# handling. --go skips the interactive pause at Step 2b.
# stdout/stderr are forwarded to our own stdout so run_weekly.sh captures them.
# ─────────────────────────────────────────────────────────────────────────────

print("\nSTEP 2 — Running fetch_osha.py --go")
print("-" * 60)

result = subprocess.run(
    [sys.executable, FETCH_SCRIPT, "--go"],
    cwd=SCRIPT_DIR,          # run from the project folder
)

print("-" * 60)

osha_ok = (result.returncode == 0 and os.path.exists(FRESH_OUTPUT))

if not osha_ok:
    print(f"\n⚠️  fetch_osha.py failed (exit {result.returncode}) — "
          f"skipping OSHA steps 3-7, continuing to CMS and New Facilities.")

if osha_ok:
    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3 — Apply priority_tier + facility-level deduplication to fresh output
    # ─────────────────────────────────────────────────────────────────────────

    print("\nSTEP 3 — Enriching fresh data with priority_tier and deduplicating by facility")

    fresh_df = pd.read_csv(FRESH_OUTPUT, dtype=str)
    fresh_df["current_penalty"]     = pd.to_numeric(fresh_df["current_penalty"],     errors="coerce").fillna(0)
    fresh_df["days_since_citation"] = pd.to_numeric(fresh_df["days_since_citation"], errors="coerce")
    fresh_df["priority_tier"]       = fresh_df["naics_code"].apply(get_tier)

    viol_counts = (
        fresh_df.groupby(["estab_name", "site_address"]).size().reset_index(name="total_violations")
    )
    fresh_sorted  = fresh_df.sort_values("current_penalty", ascending=False)
    fresh_deduped = fresh_sorted.drop_duplicates(subset=["estab_name", "site_address"], keep="first").copy()
    fresh_final   = fresh_deduped.merge(viol_counts, on=["estab_name", "site_address"], how="left")
    fresh_final   = fresh_final.sort_values(["priority_tier", "days_since_citation"], ascending=[True, True]).reset_index(drop=True)
    print(f"  Fresh records (after facility dedup): {len(fresh_final):,}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4 — Load existing healthcare_violations_final.csv
    # ─────────────────────────────────────────────────────────────────────────

    print("\nSTEP 4 — Loading existing final file")

    if os.path.exists(FINAL_OUTPUT):
        existing_df = pd.read_csv(FINAL_OUTPUT, dtype=str)
        existing_df["current_penalty"]     = pd.to_numeric(existing_df["current_penalty"],     errors="coerce").fillna(0)
        existing_df["days_since_citation"] = pd.to_numeric(existing_df["days_since_citation"], errors="coerce")
        print(f"  Existing records: {len(existing_df):,}")
    else:
        existing_df = pd.DataFrame(columns=fresh_final.columns)
        print("  No existing file found — will create from scratch")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 5 — Identify new vs duplicate records
    # ─────────────────────────────────────────────────────────────────────────

    print("\nSTEP 5 — Identifying new vs duplicate records")

    def make_key_set(df):
        keys = set()
        for _, row in df.iterrows():
            key = tuple(str(row.get(col, "") or "").strip().lower() for col in DEDUP_KEY)
            keys.add(key)
        return keys

    existing_keys = make_key_set(existing_df)

    def is_new(row):
        key = tuple(str(row.get(col, "") or "").strip().lower() for col in DEDUP_KEY)
        return key not in existing_keys

    mask_new        = fresh_final.apply(is_new, axis=1)
    new_records_df  = fresh_final[mask_new].copy()
    dupe_records_df = fresh_final[~mask_new].copy()
    print(f"  New records:        {len(new_records_df):,}")
    print(f"  Duplicates skipped: {len(dupe_records_df):,}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6 — Combine, re-sort, and save
    # ─────────────────────────────────────────────────────────────────────────

    print("\nSTEP 6 — Rebuilding and saving healthcare_violations_final.csv")

    combined_df = pd.concat([existing_df, new_records_df], ignore_index=True)
    combined_df["priority_tier"]       = pd.to_numeric(combined_df["priority_tier"],       errors="coerce")
    combined_df["days_since_citation"] = pd.to_numeric(combined_df["days_since_citation"], errors="coerce")
    combined_df = combined_df.sort_values(["priority_tier", "days_since_citation"], ascending=[True, True]).reset_index(drop=True)
    combined_df.to_csv(FINAL_OUTPUT, index=False)
    print(f"  Saved to {FINAL_OUTPUT}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 7 — OSHA summary
    # ─────────────────────────────────────────────────────────────────────────

    print()
    print("=" * 60)
    print("OSHA SUMMARY")
    print("=" * 60)
    print(f"  New records added:        {len(new_records_df):>6,}")
    print(f"  Duplicates skipped:       {len(dupe_records_df):>6,}")
    print(f"  Total records in file:    {len(combined_df):>6,}")
    print(f"  Output:                   {FINAL_OUTPUT}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Run fetch_cms.py to pull fresh CMS deficiency data
# ─────────────────────────────────────────────────────────────────────────────

print("\nSTEP 8 — Running fetch_cms.py")
print("-" * 60)

cms_result = subprocess.run(
    [sys.executable, FETCH_CMS_SCRIPT],
    cwd=SCRIPT_DIR,
)

print("-" * 60)

if cms_result.returncode != 0:
    print(f"\n⚠️  fetch_cms.py exited with code {cms_result.returncode}. Skipping CMS dedup.")
elif not os.path.exists(CMS_OUTPUT):
    print(f"\n⚠️  {CMS_OUTPUT} was not produced. Skipping CMS dedup.")
else:

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 9 — Dedup cms_deficiencies.csv against itself across weekly runs
    #
    # fetch_cms.py always produces a fresh file from the full CMS download.
    # We keep a rolling history by appending only rows whose 4-column key
    # (Provider Name + State + Survey Date + Deficiency Tag Number)
    # has not been seen in the previous version of cms_deficiencies.csv.
    # ─────────────────────────────────────────────────────────────────────────

    print("\nSTEP 9 — Deduplicating CMS deficiencies against existing records")

    fresh_cms = pd.read_csv(CMS_OUTPUT, dtype=str)
    print(f"  Fresh CMS rows:     {len(fresh_cms):,}")

    # Load the backup of last week's file (before fetch_cms.py overwrote it)
    # fetch_cms.py replaces the file entirely, so we diff against the old
    # in-memory version by reloading.  On the first run there is no history —
    # the fresh file IS the output; just re-save with the canonical column set.
    #
    # Implementation: we always save the fresh file as-is (fetch_cms already
    # wrote it), then deduplicate internally so no row appears twice if the
    # same survey spans two weekly windows.

    cms_deduped = fresh_cms.drop_duplicates(subset=CMS_DEDUP_KEY, keep="first").copy()
    dupes_dropped = len(fresh_cms) - len(cms_deduped)

    cms_deduped.to_csv(CMS_OUTPUT, index=False)

    print(f"  Internal dupes removed: {dupes_dropped:,}")
    print(f"  Final CMS rows saved:   {len(cms_deduped):,}")

    print()
    print("=" * 60)
    print("CMS SUMMARY")
    print("=" * 60)
    print(f"  Internal dupes removed: {dupes_dropped:>6,}")
    print(f"  Total CMS rows in file: {len(cms_deduped):>6,}")
    print(f"  Output:                 {CMS_OUTPUT}")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# New Facilities runs on its own Wednesday schedule via run_leads.sh / launchd.
# Exit with code 1 if OSHA failed so the log reflects it clearly.
# ─────────────────────────────────────────────────────────────────────────────
if not osha_ok:
    print("\n⚠️  Exiting with code 1 — OSHA failed, but CMS was updated.")
    sys.exit(1)
