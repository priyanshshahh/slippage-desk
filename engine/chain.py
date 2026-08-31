"""Option chain retrieval, OCC symbol parsing, and liquidity filtering.

Fill quality dominates edge over a short horizon, so the liquidity gates
here are deliberately strict. A theoretically good spread that costs two
ticks of slippage on entry and exit is not a good spread.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from alpaca.data.requests import OptionChainRequest
from alpaca.data.enums import OptionsFeed

from engine.client import option_data, options_feed

OCC = re.compile(r"^(?P<root>[A-Z]+)(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


@dataclass(frozen=True)
class Contract:
    """One option contract with everything needed to price and gate it."""

    symbol: str
    underlying: str
    expiry: date
    right: str            # "C" or "P"
    strike: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    delta: float | None
    iv: float | None

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def rel_spread(self) -> float:
        """Bid/ask width as a fraction of mid. The core liquidity metric."""
        if self.mid <= 0:
            return float("inf")
        return (self.ask - self.bid) / self.mid

    @property
    def abs_delta(self) -> float:
        return abs(self.delta) if self.delta is not None else float("nan")

    def dte(self, asof: date) -> int:
        return (self.expiry - asof).days

    @property
    def tradable(self) -> bool:
        """A quote we could actually transact against."""
        return self.bid > 0 and self.ask > 0 and self.ask > self.bid


def parse_occ(symbol: str) -> tuple[str, date, str, float] | None:
    m = OCC.match(symbol)
    if not m:
        return None
    exp = datetime.strptime(m["exp"], "%y%m%d").date()
    return m["root"], exp, m["cp"], int(m["strike"]) / 1000.0


def _feed() -> OptionsFeed:
    return OptionsFeed.OPRA if options_feed() == "opra" else OptionsFeed.INDICATIVE


def fetch_chain(
    underlying: str,
    min_dte: int,
    max_dte: int,
    asof: date | None = None,
) -> list[Contract]:
    """Pull the chain for one underlying, restricted to a DTE band."""
    asof = asof or date.today()
    req = OptionChainRequest(underlying_symbol=underlying, feed=_feed())
    snapshots = option_data().get_option_chain(req)

    out: list[Contract] = []
    for symbol, snap in snapshots.items():
        parsed = parse_occ(symbol)
        if not parsed:
            continue
        root, expiry, right, strike = parsed

        dte = (expiry - asof).days
        if dte < min_dte or dte > max_dte:
            continue

        quote = getattr(snap, "latest_quote", None)
        if quote is None:
            continue

        greeks = getattr(snap, "greeks", None)

        out.append(
            Contract(
                symbol=symbol,
                underlying=root,
                expiry=expiry,
                right=right,
                strike=strike,
                bid=float(getattr(quote, "bid_price", 0) or 0),
                ask=float(getattr(quote, "ask_price", 0) or 0),
                bid_size=float(getattr(quote, "bid_size", 0) or 0),
                ask_size=float(getattr(quote, "ask_size", 0) or 0),
                delta=float(greeks.delta) if greeks and greeks.delta is not None else None,
                iv=(
                    float(snap.implied_volatility)
                    if getattr(snap, "implied_volatility", None) is not None
                    else None
                ),
            )
        )
    return out


def liquid(contracts: list[Contract], max_rel_spread: float) -> list[Contract]:
    """Keep only contracts we could realistically get filled on."""
    return [
        c
        for c in contracts
        if c.tradable and c.rel_spread <= max_rel_spread and c.bid_size > 0 and c.ask_size > 0
    ]


def implied_spot(contracts: list[Contract]) -> float | None:
    """Underlying price implied by the chain, via put-call parity.

    C - P = S - K, so the strike where call and put mids converge is the
    spot. Free, and it cannot disagree with the quotes the gates are
    already reasoning about, which a separate spot feed could.
    """
    calls = {c.strike: c.mid for c in contracts if c.right == "C" and c.tradable}
    puts = {c.strike: c.mid for c in contracts if c.right == "P" and c.tradable}
    common = set(calls) & set(puts)
    if not common:
        return None
    k = min(common, key=lambda s: abs(calls[s] - puts[s]))
    return k + calls[k] - puts[k]


def nearest_expiry(contracts: list[Contract]) -> date | None:
    expiries = sorted({c.expiry for c in contracts})
    return expiries[0] if expiries else None
