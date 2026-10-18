#!/usr/bin/env bash
# BugSmasher — demo.bash
#
# A story-time walkthrough for a 5-year-old (or anyone new).
# We pretend BugSmasher is a tiny robot that:
#   1. looks at a toy box full of toys        (sample_repo/)
#   2. finds the ones that are broken          (failing tests)
#   3. tries to fix each broken toy            (the fixer pipeline)
#   4. shows us which toys got fixed           (the dashboard)
#
# This script only *reads* the project and starts the server you already have.
# It never deletes your work. You can press Ctrl-C at any time.
#
# Usage:
#   bash demo.bash              # friendly story + launch server
#   bash demo.bash --fast       # same story, no slow typing
#   bash demo.bash --no-serve   # story only, don't start the server
#   bash demo.bash --help

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# ---- flags -------------------------------------------------------------------
FAST=0
SERVE=1
for arg in "$@"; do
  case "$arg" in
    --fast)     FAST=1 ;;
    --no-serve) SERVE=0 ;;
    -h|--help)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown flag: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# ---- pretty printing ---------------------------------------------------------
# invariant: every narrator line goes through say() so --fast toggles uniformly
BOLD=$'\033[1m'; CYAN=$'\033[36m'; GREEN=$'\033[32m'
YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; OFF=$'\033[0m'

say()  { printf '%s%s%s\n' "$CYAN" "$*" "$OFF"; [ "$FAST" = 1 ] || sleep 0.6; }
step() { printf '\n%s▶ %s%s\n' "$BOLD" "$*" "$OFF"; [ "$FAST" = 1 ] || sleep 0.4; }
ok()   { printf '  %s✓%s %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$OFF" "$*"; }
bad()  { printf '  %s✗%s %s\n' "$RED"    "$OFF" "$*"; }
hr()   { printf '%s────────────────────────────────────────────%s\n' "$DIM" "$OFF"; }

# ---- story -------------------------------------------------------------------
clear 2>/dev/null || true
cat <<'BANNER'
   ____             ____                     _
  | __ ) _   _  __ _/ ___| _ __ ___   __ _ _| |__   ___ _ __
  |  _ \| | | |/ _` \___ \| '_ ` _ \ / _` (_) '_ \ / _ \ '__|
  | |_) | |_| | (_| |___) | | | | | | (_| | | | | |  __/ |
  |____/ \__,_|\__, |____/|_| |_| |_|\__,_|_|_| |_|\___|_|
               |___/        a friendly bug-fixing robot
BANNER
echo

say "Hi! I'm BugSmasher. I'm a tiny robot that fixes broken code."
say "Pretend code is a box of toys. Some toys are broken. I fix them."
hr

# ---- step 1: show the toy box -----------------------------------------------
step "Step 1 — Look inside the toy box"
say  "The toy box is called 'sample_repo'. It has one toy: calculator.py"
if [ -f sample_repo/calculator.py ]; then
  ok "found the toy box"
  echo
  printf '  %s%s%s\n' "$DIM" "----- sample_repo/calculator.py -----" "$OFF"
  sed 's/^/    /' sample_repo/calculator.py
  printf '  %s%s%s\n' "$DIM" "-------------------------------------" "$OFF"
else
  bad "sample_repo/calculator.py is missing — is this the project root?"
  exit 1
fi

say "See the little notes that say 'BUG A', 'BUG B', 'BUG C', 'BUG D'?"
say "Those are the broken parts. Four tiny mistakes hiding in the toy."

# ---- step 2: prove the toys are broken --------------------------------------
step "Step 2 — Shake the toy and see what falls off (run the tests)"
say  "The tests are little helpers that press every button on the toy."
say  "If a button doesn't work, the test shouts. Let's listen..."

if [ ! -x .venv/bin/python ] || [ ! -f .venv/bin/activate ]; then
  warn "no .venv yet — I'll ask install.bash to build one (one-time setup)"
  bash "$HERE/install.bash" --no-optional >/dev/null 2>&1 \
    || { bad "install.bash failed — run it directly to see the error"; exit 1; }
  ok "venv ready"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# invariant: we intentionally expect failures here (seeded bugs) — don't abort
set +e
pytest_output="$(cd sample_repo && python -m pytest -q --no-header --color=no 2>&1)"
pytest_rc=$?
set -e

# count pass/fail from the pytest summary line
passed="$(echo "$pytest_output" | grep -Eo '[0-9]+ passed' | head -1 | awk '{print $1}')"
failed="$(echo "$pytest_output" | grep -Eo '[0-9]+ failed' | head -1 | awk '{print $1}')"
passed="${passed:-0}"; failed="${failed:-0}"

echo
printf '  tests passed: %s%s%s\n'   "$GREEN"  "$passed" "$OFF"
printf '  tests failed: %s%s%s   %s(these are the broken parts!)%s\n' \
       "$RED" "$failed" "$OFF" "$DIM" "$OFF"

if [ "$failed" = "0" ]; then
  warn "no broken toys found — the demo is less fun without bugs!"
else
  ok "found $failed broken parts — perfect, now I have something to fix"
fi

# ---- step 3: meet the fixers ------------------------------------------------
step "Step 3 — Meet my helpers (the fixers)"
say  "I don't fix toys alone. I have little helpers. Each one is good at one thing."
echo
for f in harness/fixers/*.py; do
  name="$(basename "$f" .py)"
  case "$name" in
    __init__|base|_llm) continue ;;
    offline) desc="tries fixes without the internet (safe + fast)" ;;
    gemini)  desc="asks Google's Gemini brain for a fix idea"       ;;
    nebius)  desc="asks a Nebius AI brain for a fix idea"           ;;
    *)       desc="a fixer helper" ;;
  esac
  printf '  %s•%s %-10s %s%s%s\n' "$CYAN" "$OFF" "$name" "$DIM" "$desc" "$OFF"
done

# ---- step 4: how a fix goes to production ----------------------------------
step "Step 4 — The safety rules (so nothing bad ships)"
say  "Before any fix is kept, it has to pass FOUR safety gates:"
echo "    1. prequalify   — is this change small and simple?"
echo "    2. test oracle  — do ALL the tests pass after the fix?"
echo "    3. security     — no secrets, no scary code patterns?"
echo "    4. canary SLO   — does it still behave well under load?"
say  "If any gate says NO, the fix is thrown away. Nothing broken ever ships."

# ---- step 5: show them the dashboard ---------------------------------------
step "Step 5 — Open the dashboard and watch me work"

if [ "$SERVE" = "0" ]; then
  say "You said --no-serve, so I'll stop here. To watch the robot work, run:"
  printf '    %sbash run.bash%s\n' "$BOLD" "$OFF"
  printf '    then open %shttp://127.0.0.1:8099%s in your browser\n' "$BOLD" "$OFF"
  exit 0
fi

PORT="${PORT:-8099}"
# invariant: pick a free port automatically if the default is busy, so the demo
# doesn't die with a confusing EADDRINUSE for a kid audience
if command -v lsof >/dev/null 2>&1; then
  while lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; do
    PORT=$((PORT + 1))
    [ "$PORT" -gt 8199 ] && { bad "no free port in 8099-8199"; exit 1; }
  done
fi
export PORT

say "I'll open the dashboard on http://127.0.0.1:${PORT}"
say "In the dashboard you can press 'Run' and watch me fix the broken toys live."
say "Press Ctrl-C here when you're done — that turns me off nicely."
echo

hr
# hand off to run.bash — exec so Ctrl-C goes straight to uvicorn
exec bash "$HERE/run.bash"
