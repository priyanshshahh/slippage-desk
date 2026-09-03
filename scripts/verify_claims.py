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

# Comparative claims are banned from every shipped artifact. The survey of
# other entries was internal research used to steer the build, never a public
# argument, and this repository is public. These patterns are deliberately
# narrow so ordinary words survive: "order submission" and "pre-submission
# checklist" must not trip, while "47 other submissions" must.
FORBIDDEN = [
    (r"\b\d+\s+(?:other\s+)?submissions\b", "counts other entries"),
    (r"\bread all\s+(?:\d+\s+)?(?:other\s+)?submissions\b", "claims to have read the field"),
    (r"\bother (?:agents?|teams?|entrants?|submissions?)\b", "refers to other entries"),
    (r"\b(?:nobody|no one) else\b", "claims uniqueness by comparison"),
    (r"\beveryone else\b", "compares against the field"),
    (r"\bevery other agent\b", "compares against the field"),
    (r"\bthe field (?:splits|opens|does|is)\b", "characterises the field"),
    (r"\bcompetitors?\b", "names competitors"),
    # "other entrant/team/agent" was already banned; this catches the same
    # claim phrased without "other", e.g. "any entrant claiming otherwise is
    # reading noise", which sat in WRITEUP.md for a day before a manual sweep
    # (not this list) caught it.
    (r"\b(?:any|most|some) entrants?\b", "refers to other entries"),
    (r"\bentrants? (?:claim|claiming|skip)\b", "refers to other entries"),
    # A superiority claim doesn't need to say "other" to imply comparison.
    # "nobody measures it" and "every agent in this field" both sat in
    # README.md, the first thing GitHub shows, until a manual sweep caught
    # them; neither matched anything above.
    (r"\bnobody measures\b", "implicit superiority claim"),
    (r"\bevery (?:agent|entrant|team) in this (?:field|hackathon)\b",
     "refers to other entries"),
]


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

    # The trade's arithmetic. Every published copy of it was hand-typed once
    # and described a $38 credit against a $75 stop, matching neither the
    # config nor a single fill. scripts/proof.py now derives it; these checks
    # make sure no deliverable restates it from memory again.
    ec = proof.get("economics") or {}
    if not ec:
        raise SystemExit("data/proof.json has no economics block; run scripts.proof")
    cost_per_contract = t["given_up_to_execution_usd"] / ec["contracts"]
    eaten = round(cost_per_contract / ec["expected_per_contract_usd"] * 100)

    # (label, regex that finds a claim, the value the claim must carry)
    checks = [
        ("gate count (word)", r"\b(twelve|thirteen|fourteen|fifteen|sixteen)\b(?=[^.\n]{0,40}?(?:deterministic|gates|checks))",
         WORDS[n_gates]),
        ("capture percent", r"\b(\d{2}(?:\.\d)?)%(?=[^.\n]{0,40}(?:broker-verified|of theoretical))", f"{capture * 100:.1f}"),
        ("lost to execution", r"\$(\d[\d,]*)(?=\s*(?:surrender|lost|given up|to execution))",
         f"{t['given_up_to_execution_usd']:.0f}"),
        # Two separate misses here, both real. The old pattern required the
        # number to sit immediately before the word, so it never looked inside
        # a stat card where markup separates them, and \d{3,4} could not see a
        # thousands separator, so "1,208" would have matched as "208" and
        # passed. build_deck.py drifted to a live journal count of 1,208 while
        # every other deliverable said 693, and this check watched it happen.
        ("candidates considered",
         r"\b(\d[\d,]{2,6})\b(?=\s*(?:candidates|considered))",
         f"{t['candidates_considered']:,}"),
        ("candidates considered (stat card)",
         r"Considered</div>\s*<div class=\"v\">([\d,]+)<",
         f"{t['candidates_considered']:,}"),
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
        # Spelled-out numbers hid from every check above, so a wrong figure
        # could be read aloud on camera long after the digits were fixed.
        ("veto-only count (word)",
         r"\b(ten|eleven|twelve)\b(?=[^.\n]{0,40}(?:veto|govern an LLM))",
         "eleven"),
        # Derived economics. Nothing below may be typed by hand.
        ("win per contract", r"\$(\d+\.\d\d)(?=[^.\n]{0,25}(?:on a win|banks))", f"{ec['win_usd']:.2f}"),
        ("stop cost", r"stop costs[^$\n]{0,12}\$(\d+\.\d\d)", f"{ec['loss_usd']:.2f}"),
        ("breakeven win rate", r"[Bb]reakeven(?:[^.\n]{0,20})?\s(\d{2}\.\d)%", f"{ec['breakeven_win_rate'] * 100:.1f}"),
        ("delta-implied OTM", r"[Dd]elta-implied OTM(?:[^.\n]{0,12})?\s(\d{2})%", f"{ec['delta_implied_otm_rate'] * 100:.0f}"),
        ("edge points", r"edge is\s+(\d+(?:\.\d)?)\s+percentage points", str(ec["edge_points"])),
        ("credit per contract", r"about \$(\d+) per contract", f"{ec['credit_per_contract_usd']:.0f}"),
        ("expected per contract", r"worth\s+\$(\d+\.\d\d)\s+a contract", f"{ec['expected_per_contract_usd']:.2f}"),
        ("share of edge eaten", r"(\d+)% of the edge", str(eaten)),
        # SUBMISSION.md shipped "24 contracts" against a proof that says 23,
        # in the one document a judge reads first.
        ("contracts filled", r"\b(\d+) contracts\b", str(ec["contracts"])),
        # "428 cleared every risk gate" and "20 traded" sat in SOCIAL.md for a
        # day: a gate-clearance count proof.json has never recorded, and a
        # stale fill count, both phrased just differently enough that neither
        # the considered-check nor the ban list above caught them.
        ("orders filled (traded/cleared)",
         r"\b(\d[\d,]{0,4})\s+(?:cleared every (?:risk )?gate|actually traded|traded\b)",
         str(t["orders_filled"])),
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
          f"{t['candidates_considered']} considered")
    # Comparative claims are banned outright, so the sweep reports every hit
    # rather than checking a value. The survey that produced them was internal.
    # The two build scripts are swept as well: they generate the film and its
    # narration, which no other check in this file ever reads, so a comparison
    # reintroduced there would ship on camera unseen.
    for rel in DOCS:
        f = ROOT / rel
        if f.exists() and re.search(r"\b\d+\s+(?:approved|cleared the gates)\b",
                                    f.read_text()):
            problems.append(
                f"  {rel}: claims a gate-clearance count. data/proof.json does "
                f"not record one, so it cannot be verified and drifts silently")

    # Every shipped text, not just the docs. The comparison ban was originally
    # scoped to docs plus three build scripts, and a comparative claim sat in
    # engine/assignment.py's module docstring the whole time. The repo is
    # public, so a docstring is as published as a README.
    swept = [ROOT / rel for rel in DOCS]
    for sub in ("engine", "agent", "scripts"):
        swept += sorted((ROOT / sub).rglob("*.py"))
    swept += sorted((ROOT / "dashboard" / "src").rglob("*.tsx"))
    swept += sorted((ROOT / "dashboard" / "src").rglob("*.ts"))
    swept.append(ROOT / "README.md")
    for f in swept:
        if not f.exists() or f.name == "verify_claims.py":
            continue                      # this file defines the patterns
        rel = f.relative_to(ROOT)
        body = f.read_text()
        for pattern, why in FORBIDDEN:
            for m in re.finditer(pattern, body, re.I):
                line = body[: m.start()].count("\n") + 1
                problems.append(
                    f"  {rel}:{line}  comparative claim {m.group(0)!r}: {why}")

    if problems:
        print(f"\nDRIFT: {len(problems)} claim(s) disagree with source\n")
        print("\n".join(problems))
        return 1
    print(f"\nall claims across {len(DOCS)} deliverables agree with source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
