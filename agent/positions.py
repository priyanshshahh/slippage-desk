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
    width: float = 0.0          # strike distance; 0 means derive it from OCC

    @property
    def expiry_date(self) -> date:
        return date.fromisoformat(self.expiry)

    @property
    def symbols(self) -> list[str]:
        """Short leg first. close_spread() relies on that order."""
        return [self.short_symbol, self.long_symbol]

    @property
    def strike_width(self) -> float:
        """Exact strike distance, recovered from the OCC symbols if unset.

        Reconstructing it as max_loss/100 + entry_credit mixes a mid-based max
        loss with an actual fill credit, so it is off by the slippage.
        """
        if self.width:
            return self.width
        from engine.chain import parse_occ
        a, b = parse_occ(self.short_symbol), parse_occ(self.long_symbol)
        if a and b:
            return abs(a[3] - b[3])
        return self.max_loss_per_contract / 100.0 + self.entry_credit

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


def reconcile(broker_symbols: set[str],
              broker_qty: dict[str, int] | None = None) -> list[OpenSpread]:
    """Make the ledger agree with the broker. The broker is the truth.

    Two failure modes, both seen live on 2026-08-31:

    1. A spread that expired, was closed by hand, or was liquidated vanishes
       from the broker. Keeping it inflates open risk and blocks new trades.

    2. Far worse: trading the SAME strike repeatedly overwrote the ledger row
       instead of accumulating it, because rows are keyed on the short leg.
       The ledger read 1 contract while the broker held 8, so open_risk was
       understated by roughly $2,700 and the portfolio gate believed it had
       headroom it did not have. The agent then concentrated eight contracts
       into one strike.

    Quantity now comes from the broker on every poll. A ledger that can
    disagree with the broker about size is not a risk control.
    """
    kept, dropped, corrected = [], [], []
    for s in load():
        if s.short_symbol not in broker_symbols:
            dropped.append(s)
            continue
        if broker_qty is not None:
            actual = abs(broker_qty.get(s.short_symbol, s.contracts))
            if actual and actual != s.contracts:
                corrected.append((s.short_symbol, s.contracts, actual))
                s.contracts = actual
        kept.append(s)

    if dropped or corrected:
        save(kept)
    if corrected:
        for sym, was, now in corrected:
            print(f"  ledger corrected: {sym} {was}x -> {now}x (broker)")
    return dropped
