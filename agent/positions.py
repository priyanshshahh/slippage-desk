"""Ledger of open spreads.

The broker reports option legs individually, so it can tell us we are long
one contract and short another but not that the two are one defined-risk
package opened for a known credit. Exits need that credit: "take profit at
50%" is meaningless without the number the position was opened at.

The broker stays the source of truth for what is open. This file only adds
the entry context the broker does not keep, and anything the broker no
longer reports is dropped on reconcile.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone

from engine.config import ROOT

LEDGER = ROOT / "data" / "open_spreads.json"


@dataclass
class OpenSpread:
    underlying: str
    kind: str
    expiry: str                 # ISO date
    short_symbol: str
    long_symbol: str
    contracts: int
    entry_credit: float         # per share, what we actually took in
    max_loss_per_contract: float
    bucket: str                 # execution-quality bucket key
    opened_at: str              # ISO timestamp, UTC
    order_id: str = ""

    @property
    def expiry_date(self) -> date:
        return date.fromisoformat(self.expiry)

    @property
    def symbols(self) -> list[str]:
        """Short leg first. close_spread() relies on that order."""
        return [self.short_symbol, self.long_symbol]

    @property
    def risk(self) -> float:
        return self.contracts * self.max_loss_per_contract


def load() -> list[OpenSpread]:
    if not LEDGER.exists():
        return []
    with open(LEDGER) as fh:
        return [OpenSpread(**row) for row in json.load(fh)]


def save(spreads: list[OpenSpread]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "w") as fh:
        json.dump([asdict(s) for s in spreads], fh, indent=2)


def add(spread: OpenSpread) -> None:
    current = load()
    current.append(spread)
    save(current)


def remove(short_symbol: str) -> None:
    save([s for s in load() if s.short_symbol != short_symbol])


def opened_on(day: date) -> int:
    """How many spreads were opened on a given date, for the daily cap."""
    return sum(
        1
        for s in load()
        if datetime.fromisoformat(s.opened_at).astimezone(timezone.utc).date() == day
    )


def reconcile(broker_symbols: set[str]) -> list[OpenSpread]:
    """Drop ledger rows the broker no longer reports.

    A spread that expired worthless, was closed by hand, or was liquidated
    disappears from the broker. Keeping it would inflate open risk and
    silently block new trades.
    """
    kept, dropped = [], []
    for s in load():
        if s.short_symbol in broker_symbols:
            kept.append(s)
        else:
            dropped.append(s)
    if dropped:
        save(kept)
    return dropped
