"""Stamp the current evidence into the slide deck.

The deck originally fetched its numbers at render time, which fails on a
file:// URL and produced an empty stats slide. Presentation artefacts should
not depend on a network call, so the numbers are written into the HTML.

Re-run before exporting the PDF so the deck matches the account.

    python -m scripts.build_deck
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import re
import sys

from engine import journal
from engine.config import ROOT

DECK = ROOT / "docs" / "slides.html"
COVER = ROOT / "docs" / "cover.html"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"



def _chrome(*args: str) -> bool:
    """Render through headless Chrome, reporting honestly if it is absent.

    The deck and cover used to be exported by hand, which is how the cover
    shipped once with two stats transposed. A missing Chrome is not fatal to
    the rest of the build, but it must not be silent either.
    """
    if not pathlib.Path(CHROME).exists():
        print(f"  ! Chrome not found at {CHROME}; skipped render")
        return False
    r = subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars", *args],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  ! Chrome exited {r.returncode}: {r.stderr.strip()[:200]}")
        return False
    return True


def stamp_cover(proof: dict, n_gates: int) -> None:
    """Write the measured numbers into every id="x-*" slot on the cover."""
    t, bv = proof["totals"], proof["broker_verification"]
    capture = bv["broker_capture_ratio"] or t["aggregate_capture_ratio"] or 0
    values = {
        "x-capture": f"{capture * 100:.1f}%",
        "x-spreads": str(bv["paired_spreads"]),
        "x-gates": str(n_gates),
        "x-surfaces": "3",
        "x-theoretical": f"${t['theoretical_credit_usd']:,.0f}",
        "x-captured": f"${t['captured_credit_usd']:,.0f}",
        "x-lost": f"${t['given_up_to_execution_usd']:,.0f}",
    }
    html = COVER.read_text()
    for key, val in values.items():
        html, n = re.subn(rf'(id="{key}"[^>]*>)[^<]*(<)', rf"\g<1>{val}\g<2>", html)
        if n != 1:
            raise SystemExit(f"cover.html: expected one {key} slot, found {n}")
    html, n = re.subn(
        r'(id="x-barwidth" style="width:)[^%]*(%)', rf"\g<1>{capture * 100:.1f}\g<2>", html
    )
    if n != 1:
        raise SystemExit(f"cover.html: expected one x-barwidth slot, found {n}")
    COVER.write_text(html)


def main() -> int:
    proof = json.loads((ROOT / "data" / "proof.json").read_text())
    t, bv = proof["totals"], proof["broker_verification"]
    capture = bv["broker_capture_ratio"] or t["aggregate_capture_ratio"] or 0

    # These two used to come from journal.summary(), which reads the live
    # journal and keeps counting while the agent runs. The deck therefore
    # printed 1,208 considered while data/proof.json, the video and every
    # other deliverable said 693, and a judge opening both would have found
    # the pitch disagreeing with its own signed evidence. Everything now
    # quotes the frozen artifact, which is the whole point of signing one.
    cards = [
        ("Considered", f"{t['candidates_considered']:,}", "candidates evaluated"),
        ("Spreads filled", f"{bv['paired_spreads']:,}", "broker-paired, all fifteen gates"),
        ("Credit captured", f"{capture * 100:.1f}%", "broker-verified"),
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
    # Both judge-facing images are rendered here, so neither can be forgotten
    # or exported from a stale copy of the page.
    n_gates = len({
        node.args[0].value
        for node in ast.walk(ast.parse((ROOT / "engine" / "risk.py").read_text()))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "Verdict"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value != "model_opinion"
    })
    stamp_cover(proof, n_gates)

    pdf = ROOT / "docs" / "slides.pdf"
    if _chrome("--no-pdf-header-footer", f"--print-to-pdf={pdf}", DECK.as_uri()):
        print(f"  deck pdf   {pdf.relative_to(ROOT)}  ({pdf.stat().st_size // 1024} KB)")

    png = ROOT / "docs" / "cover.png"
    if _chrome("--force-device-scale-factor=2", "--window-size=1280,720",
               f"--screenshot={png}", COVER.as_uri()):
        print(f"  cover png  {png.relative_to(ROOT)}  ({png.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
