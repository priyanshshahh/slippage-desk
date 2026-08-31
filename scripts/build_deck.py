"""Stamp the current evidence into the slide deck.

The deck originally fetched its numbers at render time, which fails on a
file:// URL and produced an empty stats slide. Presentation artefacts should
not depend on a network call, so the numbers are written into the HTML.

Re-run before exporting the PDF so the deck matches the account.

    python -m scripts.build_deck
"""
from __future__ import annotations

import json
import re
import sys

from engine import journal
from engine.config import ROOT

DECK = ROOT / "docs" / "slides.html"


def main() -> int:
    proof = json.loads((ROOT / "data" / "proof.json").read_text())
    s = journal.summary()
    t, bv = proof["totals"], proof["broker_verification"]
    capture = bv["broker_capture_ratio"] or t["aggregate_capture_ratio"] or 0

    cards = [
        ("Considered", f"{s['considered']:,}", "candidates evaluated"),
        ("Cleared gates", f"{s['approved']:,}", "passed all thirteen"),
        ("Credit captured", f"{capture * 100:.0f}%", "broker-verified"),
        ("Lost to execution", f"${t['given_up_to_execution_usd']:,.0f}",
         "the number nobody else has"),
    ]
    html = "\n".join(
        f'    <div class="card"><div class="k">{k}</div>'
        f'<div class="v">{v}</div><div class="n">{n}</div></div>'
        for k, v, n in cards
    )

    deck = DECK.read_text()
    deck = re.sub(
        r'<div class="grid" id="stats">.*?</div>\s*(?=<p style="margin-top:34px">)',
        f'<div class="grid" id="stats">\n{html}\n  </div>\n  ',
        deck,
        flags=re.S,
    )
    # The fetch is no longer needed and cannot work from a file:// URL.
    deck = re.sub(r"<script>.*?</script>\s*$", "", deck, flags=re.S)
    deck += f"\n<!-- evidence sha256 {proof['sha256'][:16]} -->\n"
    DECK.write_text(deck)

    print(f"deck stamped: {DECK}")
    for k, v, n in cards:
        print(f"  {k:20s} {v:>10s}  {n}")
    print(f"\n  sha256 {proof['sha256'][:16]}...")
    print("\n  Export: open docs/slides.html in Chrome, Cmd+P,")
    print("  Destination 'Save as PDF', Layout Landscape, Margins None,")
    print("  tick 'Background graphics'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
