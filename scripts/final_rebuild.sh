#!/bin/bash
# One-shot: regenerate every artifact from the final run, in dependency order.
#
# Written for deadline morning. Each step below was run by hand at least once
# during the week, and hand-stepping them under time pressure is exactly how
# a stale figure ships: the deck reads proof.json, the video reads the deck's
# scene definitions, the dashboard reads the journal, and the verifiers read
# all of it. Order matters, so it lives in one file.
#
# Stops at the first failure rather than pressing on, because a half-rebuilt
# package is worse than the consistent one already published.
#
#   bash scripts/final_rebuild.sh          # full run
#   SKIP_VIDEO=1 bash scripts/final_rebuild.sh   # skip the 4-minute render
set -euo pipefail
cd "$(dirname "$0")/.."

PY="./.venv/bin/python"
say() { printf '\n=== %s ===\n' "$*"; }

set -a && . ./.env && set +a

say "0. credentials"
# The CLI exits 0 even on a 401, printing the error as JSON, so the exit code
# says nothing. Check the body instead. (engine/cli.py warns about the same
# trap from the other direction: --quiet hides this envelope entirely.)
acct=$(./bin/alpaca account get 2>&1 || true)
if printf '%s' "$acct" | grep -qi 'unauthorized\|invalid credentials'; then
  echo "FAIL: Alpaca is still rejecting the credentials in .env."
  echo "Regenerate the paper key at app.alpaca.markets and update"
  echo "ALPACA_API_KEY / ALPACA_SECRET_KEY, then re-run this."
  exit 1
fi
if ! printf '%s' "$acct" | grep -q '"equity"'; then
  echo "FAIL: unexpected response from 'alpaca account get':"
  printf '%s\n' "$acct" | head -5
  exit 1
fi
echo "broker reachable, account readable"

say "1. regenerate proof from the final run"
PYTHONPATH=. $PY -m scripts.proof

say "2. tests"
PYTHONPATH=. $PY -m scripts.loop_test | tail -2

say "3. rebuild deck, cover, slides.pdf"
PYTHONPATH=. $PY -m scripts.build_deck

say "4. rebuild the film definition"
PYTHONPATH=. $PY -m scripts.build_film

say "5. narration"
PYTHONPATH=. $PY scripts/build_narration.py

if [ "${SKIP_VIDEO:-0}" != "1" ]; then
  say "6. re-render video (headless, ~4 min, nothing on screen)"
  PYTHONPATH=. $PY -u -m scripts.render_film
else
  say "6. video render SKIPPED (SKIP_VIDEO=1)"
fi

say "7. dashboard snapshot"
( cd dashboard && node scripts/snapshot-data.mjs )

say "8. verifiers"
PYTHONPATH=. $PY -m scripts.verify_claims | tail -3
PYTHONPATH=. $PY -m scripts.check_submission | tail -3

say "DONE. Review, then commit + push + vercel deploy --prod --yes"
