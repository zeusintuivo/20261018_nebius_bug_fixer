#!/usr/bin/env bash
# BugSmasher — installer
#
# Robust, idempotent install.  Stops on first failure.  Creates .venv in the
# repo root, installs every runtime + optional dep that the harness imports,
# and seeds a .env from .env.example when the operator does not have one yet.
#
# Usage:
#   bash install.bash                 # install everything
#   bash install.bash --no-optional   # skip openai + google-genai (offline fixer only)
#   bash install.bash --recreate      # wipe .venv and start fresh
set -euo pipefail

# ---- 1. locate repo, pin pwd -------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# ---- 2. parse flags ----------------------------------------------------------
WITH_OPTIONAL=1
RECREATE=0
for arg in "$@"; do
  case "$arg" in
    --no-optional) WITH_OPTIONAL=0 ;;
    --recreate)    RECREATE=1 ;;
    -h|--help)
      # invariant: slice must cover every documented usage line (2..11)
      sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# ---- 3. tiny logger ----------------------------------------------------------
log()  { printf '\033[36m[install]\033[0m %s\n' "$*"; }
fail() { printf '\033[31m[install:FAIL]\033[0m %s\n' "$*" >&2; exit 1; }

# ---- 4. pre-flight: find a usable python3 -----------------------------------
# invariant: PY must point at an interpreter >= 3.10, else we bail cleanly
pick_python() {
  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
        echo "$candidate"; return 0
      fi
    fi
  done
  return 1
}
PY="$(pick_python)" || fail "need python >= 3.10 on PATH (tried python3.10..python3.14)"
log "using interpreter: $("$PY" -c 'import sys;print(sys.executable, sys.version.split()[0])')"

# ---- 5. venv -----------------------------------------------------------------
# invariant: after this block, .venv/bin/python exists and is executable
if [ "$RECREATE" -eq 1 ] && [ -d .venv ]; then
  log "--recreate: removing existing .venv"
  rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
  log "creating virtualenv at .venv"
  "$PY" -m venv .venv || fail "python -m venv failed (install the 'venv' module)"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
log "venv active: $(python -c 'import sys;print(sys.prefix)')"

# ---- 6. upgrade packaging tools ---------------------------------------------
log "upgrading pip / setuptools / wheel"
python -m pip install --upgrade --quiet pip setuptools wheel \
  || fail "pip bootstrap failed — check your network/proxy"

# ---- 7. runtime deps (hard requirement) --------------------------------------
# invariant: every package here is imported unconditionally by the harness
REQUIRED=(
  "fastapi>=0.110"
  "uvicorn>=0.27"
  "python-dotenv>=1.0"
  "pytest>=8.0"
  "httpx>=0.27"
)
log "installing required deps: ${REQUIRED[*]}"
# NOTE: no --quiet here on purpose; if pip breaks the user needs the traceback
python -m pip install "${REQUIRED[@]}" \
  || fail "required dependency install failed (see pip output above)"

# ---- 8. optional LLM backends -----------------------------------------------
# nebius uses the OpenAI-compatible SDK; gemini uses google-genai.  Both are
# optional — the offline fixer works without them.
if [ "$WITH_OPTIONAL" -eq 1 ]; then
  OPTIONAL=(
    "openai>=1.40"
    "google-genai>=0.3"
  )
  log "installing optional LLM backends: ${OPTIONAL[*]}"
  for pkg in "${OPTIONAL[@]}"; do
    if ! python -m pip install --quiet "$pkg"; then
      printf '\033[33m[install:WARN]\033[0m skipped %s (install manually if you need it)\n' "$pkg"
    fi
  done
else
  log "--no-optional: skipping openai / google-genai"
fi

# ---- 9. sanity import check --------------------------------------------------
# invariant: if any required module cannot be imported, run.bash will fail too,
# so we fail here instead where the message is actionable
log "verifying imports"
python - <<'PY' || fail "post-install import check failed — see traceback above"
import importlib
for m in ("fastapi", "uvicorn", "dotenv", "pytest", "httpx"):
    importlib.import_module(m)
print("  all required modules import cleanly")
PY

# ---- 10. seed .env from example if missing ----------------------------------
if [ ! -f .env ] && [ -f .env.example ]; then
  log "creating .env from .env.example (edit it to add API keys)"
  cp .env.example .env
fi

# ---- 11. done ---------------------------------------------------------------
log "install complete.  next:  bash run.bash"
