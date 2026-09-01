"""Early-assignment risk, which is the hazard this strategy actually has.

Every other agent in this hackathon gates on entry logic and position size.
None of them mention assignment. That is the largest real-world risk in
short-dated short options and it is not hypothetical:

A short call goes in-the-money. An ex-dividend date falls before expiry.
Capturing the dividend is now worth more to the holder than the remaining
extrinsic value, so they exercise early. You are assigned, and you wake up
short 100 shares of the underlying per contract, carrying an overnight gap
you never agreed to take. The spread's "defined risk" was defined against
expiry, not against being assigned three days early.

Short puts have the mirror problem near expiry when they go deep ITM and
extrinsic value collapses.

This module reads ex-dividend dates from Alpaca's corporate actions API,
refuses candidates that carry the risk, and detects assignment after the
fact by noticing equity positions the agent never opened.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from engine import cli
from engine.risk import Verdict
from engine.strategy import Spread


@dataclass(frozen=True)
class ExDivCalendar:
    """Ex-dividend dates per underlying, for the window we trade in."""

    dates: dict[str, list[date]]

    def before(self, underlying: str, expiry: date) -> date | None:
        """The next ex-dividend on or before expiry, if any."""
        today = date.today()
        for d in sorted(self.dates.get(underlying, [])):
            if today <= d <= expiry:
                return d
        return None

    @classmethod
    def fetch(cls, symbols: list[str], lookahead_days: int = 10) -> "ExDivCalendar":
        start = date.today()
        end = start + timedelta(days=lookahead_days)
        rows = cli.corporate_actions(
            symbols, start.isoformat(), end.isoformat(), types="cash_dividend"
        )
        out: dict[str, list[date]] = {}
        for row in rows:
            sym = row.get("symbol") or row.get("underlying_symbol")
            raw = row.get("ex_date") or row.get("ex_dividend_date")
            if not sym or not raw:
                continue
            try:
                out.setdefault(sym, []).append(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                continue
        return cls(out)

    @classmethod
    def empty(cls) -> "ExDivCalendar":
        return cls({})


def assignment_gate(
    spread: Spread, spot: float, exdiv: ExDivCalendar, now: datetime
) -> Verdict:
    """Refuse candidates carrying meaningful early-assignment risk.

    Two conditions, both specific to being SHORT the near leg:

    1. A short call whose strike sits at or below spot, with an ex-dividend
       before expiry. This is the classic dividend-capture assignment and
       it is the one that actually happens.
    2. Any short leg already in the money with one day or less to run,
       where extrinsic value is thin enough that exercise is rational.
    """
    short = spread.short_leg
    dte = (spread.expiry - now.date()).days
    itm = (
        spot >= short.strike if short.right == "C" else spot <= short.strike
    )

    ex = exdiv.before(spread.underlying, spread.expiry)
    if short.right == "C" and itm and ex is not None:
        return Verdict(
            "assignment_risk", False,
            f"short call {short.strike:g} is ITM (spot {spot:.2f}) with "
            f"ex-dividend {ex}: dividend-capture assignment likely",
        )

    if itm and dte <= 1:
        return Verdict(
            "assignment_risk", False,
            f"short {short.right} {short.strike:g} ITM with {dte} DTE, "
            f"extrinsic too thin to deter exercise",
        )

    detail = f"short {short.right} {short.strike:g} OTM vs spot {spot:.2f}"
    if ex is not None:
        detail += f", ex-dividend {ex} but strike not ITM"
    return Verdict("assignment_risk", True, detail)


def detect_assignment(broker_positions: list[dict], universe: list[str]) -> list[str]:
    """Equity positions the agent never opens are assignment evidence.

    This agent trades options exclusively. A share position in SPY or QQQ
    can only have arrived by being assigned, so its presence is a signal to
    surface loudly rather than a state to reconcile quietly.
    """
    hits = []
    for p in broker_positions:
        sym = p.get("symbol", "")
        if sym in universe and str(p.get("asset_class", "")).startswith("us_equity"):
            qty = float(p.get("qty", 0) or 0)
            if qty != 0:
                side = "short" if str(p.get("side", "")).lower() == "short" else "long"
                hits.append(f"{sym} {side} {abs(qty):.0f} shares (assigned)")
    return hits


def session_close(day: date) -> tuple[int, int] | None:
    """Actual close time for a session. Half days close at 13:00.

    A force-close hardcoded to 15:45 does nothing at all on a 13:00 close,
    which is exactly the day you would least want to be holding 0DTE.
    """
    try:
        rows = cli.calendar(day.isoformat(), day.isoformat())
    except Exception:                              # noqa: BLE001
        raise
    if not rows:
        # An empty result means the call failed or the day is not a session.
        # Returning None here was read by the caller as "regular close", which
        # silently restored the 15:45 force close on a half day. Signal that we
        # do not know, and let the caller fall back to the broker's own clock.
        raise LookupError(f"no calendar row for {day}")
    for row in rows:
        close = row.get("close")
        if close and ":" in str(close):
            hh, mm = str(close).split(":")[:2]
            return int(hh), int(mm)
    raise LookupError(f"calendar row for {day} has no close time")
