#!/usr/bin/env bash
# Run the intelligence pipeline manually (replaces the old cron oneliner).
# Usage:
#   ./run_pipeline.sh            — full ingest, write digest, mark seen, log output
#   ./run_pipeline.sh --dry-run  — ingest + score only (no writes, no files, no seen)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

LOG="$ROOT/data/run.log"
mkdir -p "$ROOT/data"

# Bootstrap venv on first run (so the script works out of the box).
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
    echo "[run] venv missing — creating..."
    python3 -m venv "$ROOT/.venv"
    "$ROOT/.venv/bin/python" -m pip install -q -r "$ROOT/requirements.txt"
fi

echo "[run] $(date '+%F %T') — starting pipeline (args: $*)"
"$ROOT/.venv/bin/python" "$ROOT/run_pipeline.py" "$@"
status=$?
echo "[run] $(date '+%F %T') — finished (exit $status)" >> "$LOG"
exit $status