"""Fail loudly if any number claimed in a deliverable has drifted from source.

Every stale figure that reached a deliverable in this project got there the
same way: the data moved and the prose did not. Docs are written once and
read by judges; proof.json is rewritten every run. So this compares them and
exits non-zero on drift, which is the only way the mismatch gets noticed
before a judge notices it.

Run before every submission or push.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ["docs/SUBMISSION.md", "docs/WRITEUP.md", "docs/VIDEO.md", "docs/SOCIAL.md",
        "docs/slides.html", "docs/cover.html", "README.md",
        "dashboard/src/app/claim.tsx", "dashboard/src/app/demo/deck.tsx",
        "dashboard/src/app/hero.tsx"]

# Competitor facts, each measured from the 47 scraped submissions. The count
# is the assertion; a claim that drifts from it is a claim a judge can falsify.
FIELD = {
    "competitors": 47,
    "measure_execution": 0,      # scored fills against mid, or tracked capture
    "slippage_mentioned": 4,     # all four pre-trade filters, none post-fill
    "veto_only": 11,
    "failure_behaviour": 6,
    "name_plus_tagline": 24,
    "calls_itself_options_agent": 11,
}


def gate_count() -> int:
    """Deterministic gates, counted from the code rather than from memory."""
    tree = ast.parse((ROOT / "engine" / "risk.py").read_text())
    gates = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Verdict":
            if node.args and isinstance(node.args[0], ast.Constant):
                gates.add(node.args[0].value)
            for kw in node.keywords:
                if kw.arg == "gate" and isinstance(kw.value, ast.Constant):
                    gates.add(kw.value.value)
    return len({g for g in gates if g != "model_opinion"})


WORDS = {12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen"}


def main() -> int:
    proof = json.loads((ROOT / "data" / "proof.json").read_text())
    cfg_text = (ROOT / "config.yaml").read_text()

    def cfg(key: str) -> str:
        m = re.search(rf"^\s*{key}:\s*\"?([^\s\"#]+)", cfg_text, re.M)
        if not m:
            raise SystemExit(f"config.yaml has no key {key!r}")
        return m.group(1)
    t, bv = proof["totals"], proof["broker_verification"]
    capture = bv["broker_capture_ratio"] or t["aggregate_capture_ratio"]
    n_gates = gate_count()

    # (label, regex that finds a claim, the value the claim must carry)
    checks = [
        ("gate count (word)", r"\b(twelve|thirteen|fourteen|fifteen|sixteen)\b(?=[^.\n]{0,40}?(?:deterministic|gates|checks))",
         WORDS[n_gates]),
        ("competitors read", r"(?:read all|of the|of those)\s+(\d+)\s+(?:other\s+)?submissions", str(FIELD["competitors"])),
        ("capture percent", r"\b(\d{2}(?:\.\d)?)%(?=[^.\n]{0,40}(?:broker-verified|of theoretical))", f"{capture * 100:.1f}"),
        ("lost to execution", r"\$(\d[\d,]*)(?=\s*(?:surrender|lost|given up|to execution))",
         f"{t['given_up_to_execution_usd']:.0f}"),
        ("candidates considered", r"\b(\d{3,4})\b(?=\s*(?:candidates|considered))", str(t["candidates_considered"])),
        # Config-derived. These drifted silently once already, in three docs at once.
        ("profit take", r"\b(\d{2})% of credit", f"{float(cfg('profit_take_pct')) * 100:.0f}"),
        ("advisor timeout", r"\b(\d+)-second\b(?=[^.\n]{0,30}timeout)", cfg("timeout_seconds")),
        ("short delta target", r"targeting (0\.\d+)", cfg("short_delta_target")),
        ("delta band low", r"\b(0\.\d+) to 0\.\d+ delta", cfg("short_delta_min")),
        ("delta band high", r"\b0\.\d+ to (0\.\d+) delta", cfg("short_delta_max")),
        ("force close", r"forced flat at\s*\n?\s*(\d{2}:\d{2})", cfg("force_close_time")),
        ("spread width", r"\$(\d+)-wide", f"{float(cfg('spread_width')):.0f}"),
        # Cover/deck stat cells. These are label/value pairs, and a transposed
        # pair (gates 13, surfaces 15) shipped on the cover image once.
        ("gates stat cell", r"Deterministic gates</div><div class=\"v\">(\d+)<", str(n_gates)),
        ("surfaces stat cell", r"Alpaca surfaces</div><div class=\"v\">(\d+)<", "3"),
    ]

    problems: list[str] = []
    for rel in DOCS:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text()
        for label, pattern, expected in checks:
            for m in re.finditer(pattern, text, re.I):
                got = m.group(1)
                if got.lower() != expected.lower():
                    line = text[: m.start()].count("\n") + 1
                    problems.append(f"  {rel}:{line}  {label}: found {got!r}, source says {expected!r}")

    # Em dashes are banned in every artifact this project ships.
    for rel in DOCS:
        p = ROOT / rel
        if p.exists() and "—" in p.read_text():
            n = p.read_text().count("—")
            problems.append(f"  {rel}  contains {n} em dash(es); use commas, periods or parentheses")

    print(f"source of truth: {n_gates} gates, {capture * 100:.1f}% capture, "
          f"${t['given_up_to_execution_usd']:.0f} lost, "
          f"{t['candidates_considered']} considered, {FIELD['competitors']} competitors")
    if problems:
        print(f"\nDRIFT: {len(problems)} claim(s) disagree with source\n")
        print("\n".join(problems))
        return 1
    print(f"\nall claims across {len(DOCS)} deliverables agree with source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
