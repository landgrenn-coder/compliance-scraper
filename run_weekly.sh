#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_weekly.sh — Weekly OSHA data refresh wrapper
#
# What it does:
#   1. Changes into the project directory (so all relative paths in update.py
#      resolve correctly regardless of where cron calls this script from)
#   2. Writes a timestamped START banner to update_log.txt
#   3. Runs update.py and appends its entire stdout + stderr to the log
#   4. Writes a timestamped END banner so log entries are easy to scan
#
# Usage:
#   bash run_weekly.sh                 # run manually
#   (scheduled via cron — see README comments below)
# ─────────────────────────────────────────────────────────────────────────────

# ── Resolve the directory this script lives in, even when called by cron ──
# $BASH_SOURCE[0] is the script file itself; dirname strips the filename.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# ── All output goes to update_log.txt in the same folder ──
LOG_FILE="$SCRIPT_DIR/update_log.txt"

# ── Timestamp helper — produces e.g. "2026-04-03 07:00:01" ──
timestamp() { date "+%Y-%m-%d %H:%M:%S"; }

# ── Move into the project directory ──
cd "$SCRIPT_DIR" || { echo "ERROR: cannot cd to $SCRIPT_DIR"; exit 1; }

# ── Write the run header to the log (tee so it also prints to stdout) ──
{
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  OSHA UPDATE STARTED — $(timestamp)"
  echo "════════════════════════════════════════════════════════════"
} | tee -a "$LOG_FILE"

# ── Run update.py; pipe all output (stdout + stderr) into the log ──
# 2>&1 merges stderr into stdout so error traces are captured in the log too.
python3 "$SCRIPT_DIR/update.py" 2>&1 | tee -a "$LOG_FILE"

# ── Capture the exit code from update.py (not from tee) ──
EXIT_CODE="${PIPESTATUS[0]}"

# ── Always regenerate and push — CMS/NF update even when OSHA fails ──
if true; then
  {
    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo "  REGENERATING index.html — $(timestamp)"
    echo "────────────────────────────────────────────────────────────"
  } | tee -a "$LOG_FILE"

  python3 "$SCRIPT_DIR/generate_html.py" 2>&1 | tee -a "$LOG_FILE"
  python3 "$SCRIPT_DIR/generate_leads.py" 2>&1 | tee -a "$LOG_FILE"
  GEN_CODE="${PIPESTATUS[0]}"

  if [ "$GEN_CODE" -eq 0 ]; then
    {
      echo ""
      echo "────────────────────────────────────────────────────────────"
      echo "  PUSHING TO GITHUB — $(timestamp)"
      echo "────────────────────────────────────────────────────────────"
    } | tee -a "$LOG_FILE"

    cd "$SCRIPT_DIR" || exit 1
    git add index.html healthcare_violations_final.csv cms_deficiencies.csv
    git diff --cached --quiet || git commit -m "Weekly data refresh — $(timestamp)"
    git push 2>&1 | tee -a "$LOG_FILE"
    PUSH_CODE="${PIPESTATUS[0]}"

    if [ "$PUSH_CODE" -ne 0 ]; then
      echo "  WARNING: git push failed (exit $PUSH_CODE) — data saved locally" | tee -a "$LOG_FILE"
    else
      echo "  GitHub Pages updated successfully." | tee -a "$LOG_FILE"
    fi
  else
    echo "  WARNING: generate_html.py failed — index.html not updated" | tee -a "$LOG_FILE"
  fi
fi

# ── Write the run footer ──
{
  echo ""
  echo "════════════════════════════════════════════════════════════"
  if [ "$EXIT_CODE" -eq 0 ]; then
    echo "  OSHA UPDATE COMPLETED OK — $(timestamp)"
  else
    echo "  OSHA UPDATE FAILED (exit $EXIT_CODE) — $(timestamp)"
  fi
  echo "════════════════════════════════════════════════════════════"
  echo ""
} | tee -a "$LOG_FILE"

exit "$EXIT_CODE"
