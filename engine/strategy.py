"""Construction of defined-risk short-premium spreads.

Only two structures are built, both credit, both fully covered so they
satisfy Alpaca's rule that every short leg be covered inside the same
mleg order:

  put credit spread   sell higher-strike put,  buy lower-strike put
  call credit spread  sell lower-strike call,  buy higher-strike call

An iron condor is simply both of the above on one expiry, submitted as a
single four-leg mleg order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from engine.chain import Contract


@dataclass(frozen=True)
class Spread:
    """A defined-risk vertical, priced off the quotes we would cross."""

    underlying: str
    kind: str                 # "put_credit" or "call_credit"
    short_leg: Contract
    long_leg: Contract
    expiry: date

    @property
    def width(self) -> float:
        return abs(self.short_leg.strike - self.long_leg.strike)

    @property
    def credit_mid(self) -> float:
        """Net credit at mid prices, per share."""
        return self.short_leg.mid - self.long_leg.mid

    @property
    def credit_worst(self) -> float:
        """Net credit if we cross the spread on both legs. The honest number.

        We sell the short leg at its bid and buy the long leg at its ask.
        """
        return self.short_leg.bid - self.long_leg.ask

    @property
    def max_loss(self) -> float:
        """Per contract, in dollars. This is the entire downside."""
        return max(0.0, (self.width - self.credit_mid)) * 100.0

    @property
    def max_profit(self) -> float:
        return max(0.0, self.credit_mid) * 100.0

    @property
    def credit_to_width(self) -> float:
        return self.credit_mid / self.width if self.width else 0.0

    @property
    def short_delta(self) -> float:
        return self.short_leg.abs_delta

    @property
    def slippage_cost(self) -> float:
        """Dollars per contract given up by crossing both legs on entry."""
        return max(0.0, (self.credit_mid - self.credit_worst)) * 100.0

    def describe(self) -> str:
        return (
            f"{self.underlying} {self.expiry:%m/%d} {self.kind} "
            f"{self.short_leg.strike:g}/{self.long_leg.strike:g} "
            f"credit {self.credit_mid:.2f} maxloss {self.max_loss:.0f} "
            f"delta {self.short_delta:.3f}"
        )


def _pick_short(candidates: list[Contract], target: float, lo: float, hi: float) -> Contract | None:
    """Closest contract to the target delta, inside the allowed band."""
    banded = [c for c in candidates if c.delta is not None and lo <= c.abs_delta <= hi]
    if not banded:
        return None
    return min(banded, key=lambda c: abs(c.abs_delta - target))


def build_credit_spread(
    contracts: list[Contract],
    right: str,
    cfg: dict,
) -> Spread | None:
    """Build the best single credit vertical for one right on one expiry."""
    entry = cfg["entry"]
    legs = [c for c in contracts if c.right == right]
    if not legs:
        return None

    short = _pick_short(
        legs,
        entry["short_delta_target"],
        entry["short_delta_min"],
        entry["short_delta_max"],
    )
    if short is None:
        return None

    width = float(entry["spread_width"])
    # The long leg sits further out of the money, capping the loss.
    wanted = short.strike - width if right == "P" else short.strike + width

    by_strike = {c.strike: c for c in legs}
    long_leg = by_strike.get(wanted)
    if long_leg is None:
        # Fall back to the closest available strike at or beyond the target,
        # so a non-standard strike grid does not block the trade outright.
        further = [
            c
            for c in legs
            if (c.strike <= wanted if right == "P" else c.strike >= wanted)
        ]
        if not further:
            return None
        long_leg = min(further, key=lambda c: abs(c.strike - wanted))

    if long_leg.symbol == short.symbol:
        return None

    spread = Spread(
        underlying=short.underlying,
        kind="put_credit" if right == "P" else "call_credit",
        short_leg=short,
        long_leg=long_leg,
        expiry=short.expiry,
    )
    return spread if spread.width > 0 else None


def build_candidates(contracts: list[Contract], cfg: dict) -> list[Spread]:
    """All viable credit verticals across both rights, best credit first."""
    out: list[Spread] = []
    for right in ("P", "C"):
        s = build_credit_spread(contracts, right, cfg)
        if s is not None:
            out.append(s)
    return sorted(out, key=lambda s: s.credit_to_width, reverse=True)
