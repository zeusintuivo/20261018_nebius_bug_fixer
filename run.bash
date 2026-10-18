#!/usr/bin/env bash
# BugSmasher — launcher
#
# Starts the FastAPI harness (server + SSE stream + static UI) on PORT.
# Stops cleanly on any pre-flight failure instead of leaking a half-broken
# uvicorn.  Re-runs install.bash automatically if the venv is missing.
#
# Usage:
#   bash run.bash              # default port 8099
#   PORT=8080 bash run.bash    # pick another port
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PORT="${PORT:-8099}"
LOG_LEVEL="${LOG_LEVEL:-warning}"

log()  { printf '\033[36m[run]\033[0m %s\n' "$*"; }
fail() { printf '\033[31m[run:FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

# ---- 1. venv must exist, else bootstrap -------------------------------------
# invariant: .venv/bin/python is an executable interpreter AND activate is
# sourceable; using the same probe as install.bash keeps the two scripts in sync
if [ ! -x .venv/bin/python ] || [ ! -f .venv/bin/activate ]; then
  log ".venv missing or incomplete — running install.bash"
  bash "$HERE/install.bash" || fail "install.bash failed; fix the error above and re-run"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ---- 2. verify harness entry file --------------------------------------------
# invariant: server.py lives inside harness/ and is importable from there
[ -f harness/server.py ] || fail "harness/server.py not found — is this the project root?"

# ---- 3. verify uvicorn is importable ----------------------------------------
# invariant: a broken venv must be surfaced here, not deep inside uvicorn's spawn
python -c "import uvicorn, fastapi" 2>/dev/null \
  || fail "uvicorn/fastapi missing in .venv — run: bash install.bash --recreate"

# ---- 4. port probe (best effort; skip silently if lsof/nc missing) ----------
if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
    fail "port $PORT already in use — set PORT=<n> or stop the other process"
  fi
fi

# ---- 5. launch ---------------------------------------------------------------
log "starting uvicorn on http://127.0.0.1:${PORT}  (log-level=${LOG_LEVEL})"
cd harness
exec python -m uvicorn server:app --port "$PORT" --log-level "$LOG_LEVEL"
