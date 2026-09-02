#!/bin/bash
# Regenerate the evidence artefacts and redeploy the public dashboard.
#
# The deployed page serves a snapshot bundled at build time, so it goes stale
# unless something rebuilds it. Run this at the end of each session, and once
# more before submitting.
#
#   bash scripts/refresh_evidence.sh

set -e
cd "$(dirname "$0")/.." || exit 1

echo "==> probing every Alpaca surface"
./.venv/bin/python -m scripts.surfaces

echo "==> regenerating proof artefact"
./.venv/bin/python -m scripts.proof

echo "==> stamping the deck"
./.venv/bin/python -m scripts.build_deck >/dev/null

echo "==> snapshotting journal into the dashboard build"
(cd dashboard && npm run snapshot)

echo "==> deploying"
(cd dashboard && vercel --prod --yes --scope pris-projects-ef3397a7 2>&1 \
  | grep -oE '"message": "[^"]+"' | head -1)

echo "==> committing evidence"
git add -A
SUMMARY=$(PYTHONPATH=. ./.venv/bin/python -c "
from engine import journal
s = journal.summary()
print(str(s['considered']) + ' considered, ' + str(s['traded']) + ' traded')
")
if [ -z "$SUMMARY" ]; then
  echo "    could not read journal summary, refusing to commit a blank message"
  exit 1
fi
git commit -q -m "Refresh evidence: $SUMMARY" || echo "    nothing to commit"
git push -q origin main && echo "    pushed"
echo "done"
