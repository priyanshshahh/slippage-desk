"""Append-only decision journal.

Every candidate the agent considers is written here, including the ones it
rejected and why. Rejections are the evidence that the risk layer is doing
work, so they are as valuable as fills for the write-up and the demo.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.config import ROOT
from engine.risk import Decision

JOURNAL = ROOT / "data" / "decisions.jsonl"


def record(decision: Decision, state_snapshot: dict, fill: dict | None = None,
           ts: datetime | None = None) -> None:
    """ts is for replaying or seeding history; live callers leave it None."""
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": (ts or datetime.now(timezone.utc)).isoformat(),
        "underlying": decision.spread.underlying,
        "kind": decision.spread.kind,
        "expiry": decision.spread.expiry.isoformat(),
        "short_strike": decision.spread.short_leg.strike,
        "long_strike": decision.spread.long_leg.strike,
        "short_symbol": decision.spread.short_leg.symbol,
        "long_symbol": decision.spread.long_leg.symbol,
        "credit_mid": round(decision.spread.credit_mid, 4),
        "credit_crossable": round(decision.spread.credit_worst, 4),
        "max_loss_per_contract": round(decision.spread.max_loss, 2),
        "short_delta": round(decision.spread.short_delta, 4),
        "contracts": decision.contracts,
        "allowed": decision.allowed,
        "blocked_by": decision.blocked_by,
        "verdicts": [
            {"gate": v.gate, "allowed": v.allowed, "detail": v.detail}
            for v in decision.verdicts
        ],
        "state": state_snapshot,
        "fill": fill,
    }
    with open(JOURNAL, "a") as fh:
        fh.write(json.dumps(row) + "\n")


def load() -> list[dict]:
    if not JOURNAL.exists():
        return []
    with open(JOURNAL) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summary() -> dict:
    """Counts that mean what their names say.

    Every candidate the agent evaluates is journaled, but only the best one
    per poll is actually submitted. So "the gates approved it" and "we traded
    it" are different numbers, and conflating them overstates activity by an
    order of magnitude.
    """
    rows = load()
    considered = len(rows)
    approved = sum(1 for r in rows if r["allowed"] and r["contracts"] > 0)
    traded = sum(1 for r in rows if r.get("fill"))
    blocks: dict[str, int] = {}
    for r in rows:
        for gate in r["blocked_by"]:
            blocks[gate] = blocks.get(gate, 0) + 1
    return {
        "considered": considered,
        "approved": approved,
        "traded": traded,
        "rejected": considered - approved,
        "rejections_by_gate": dict(sorted(blocks.items(), key=lambda kv: -kv[1])),
    }
