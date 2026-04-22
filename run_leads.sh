#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_leads.sh — Weekly new facility leads refresh (runs independently of OSHA/CMS)
# Scheduled: Wednesday at 7:00am via launchd
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOG_FILE="$SCRIPT_DIR/leads_log.txt"
timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

cd "$SCRIPT_DIR" || { echo "ERROR: cannot cd to $SCRIPT_DIR"; exit 1; }

{
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  LEADS UPDATE STARTED — $(timestamp)"
  echo "════════════════════════════════════════════════════════════"
} | tee -a "$LOG_FILE"

# Step 1: Scrape new facilities from NPPES
echo "" | tee -a "$LOG_FILE"
echo "  STEP 1 — Running fetch_new_facilities.py" | tee -a "$LOG_FILE"
echo "  ──────────────────────────────────────────" | tee -a "$LOG_FILE"
python3 -u "$SCRIPT_DIR/fetch_new_facilities.py" 2>&1 | tee -a "$LOG_FILE"
NF_CODE="${PIPESTATUS[0]}"

if [ "$NF_CODE" -ne 0 ]; then
  echo "  ⚠️  fetch_new_facilities.py failed (exit $NF_CODE)" | tee -a "$LOG_FILE"
else
  # Step 2: Enrich with phone + contact
  echo "" | tee -a "$LOG_FILE"
  echo "  STEP 2 — Running enrich_facilities.py" | tee -a "$LOG_FILE"
  echo "  ──────────────────────────────────────────" | tee -a "$LOG_FILE"
  python3 -u "$SCRIPT_DIR/enrich_facilities.py" 2>&1 | tee -a "$LOG_FILE"
  EN_CODE="${PIPESTATUS[0]}"

  # Step 3: Regenerate leads.html (and main dashboard)
  echo "" | tee -a "$LOG_FILE"
  echo "  STEP 3 — Regenerating leads.html" | tee -a "$LOG_FILE"
  python3 "$SCRIPT_DIR/generate_leads.py" 2>&1 | tee -a "$LOG_FILE"
  python3 "$SCRIPT_DIR/generate_html.py"  2>&1 | tee -a "$LOG_FILE"

  # Step 4: Push to GitHub
  echo "" | tee -a "$LOG_FILE"
  echo "  STEP 4 — Pushing to GitHub" | tee -a "$LOG_FILE"
  git add leads.html index.html new_facilities.csv
  git diff --cached --quiet || git commit -m "Weekly leads refresh — $(timestamp)"
  git push 2>&1 | tee -a "$LOG_FILE"
  PUSH_CODE="${PIPESTATUS[0]}"
  if [ "$PUSH_CODE" -ne 0 ]; then
    echo "  ⚠️  git push failed (exit $PUSH_CODE) — data saved locally" | tee -a "$LOG_FILE"
  else
    echo "  ✓ GitHub Pages updated." | tee -a "$LOG_FILE"
  fi
fi

{
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  LEADS UPDATE DONE — $(timestamp)"
  echo "════════════════════════════════════════════════════════════"
  echo ""
} | tee -a "$LOG_FILE"
