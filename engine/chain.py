"""Option chain retrieval, OCC symbol parsing, and liquidity filtering.

Fill quality dominates edge over a short horizon, so the liquidity gates
here are deliberately strict. A theoretically good spread that costs two
ticks of slippage on entry and exit is not a good spread.
"""
from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass
from datetime import date, datetime

from alpaca.data.requests import OptionChainRequest
from alpaca.data.enums import OptionsFeed

from engine.client import option_data, options_feed


class ChainError(RuntimeError):
    """A chain could not be retrieved. Callers treat this as one bad poll."""

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
    open_interest: float = 0.0
    volume: float = 0.0

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


CHAIN_TIMEOUT_S = 45.0


def _chain_with_deadline(req: OptionChainRequest) -> dict:
    """Fetch a chain, but never block the poll loop indefinitely.

    The SDK call carries no timeout of its own. On 2026-09-04 the agent hung
    twice, both times immediately after the connection was reset mid-fetch:
    silent for 44 minutes on the first occasion and 11 on the second, with the
    process alive and idle. A hung loop manages no exits, so a stop or the
    reporting flatten would simply never fire, which is the one failure this
    project cannot absorb on submission day.

    The work runs on a worker thread and the caller gives up at the deadline.
    A thread cannot be killed, so an abandoned one is left to finish and be
    discarded; that leaks a thread at worst, where the alternative loses the
    agent. poll_once already treats an exception as one bad poll and re-reads
    everything from the broker next time round.
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(option_data().get_option_chain, req)
        try:
            return fut.result(timeout=CHAIN_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            raise ChainError(
                f"option chain fetch exceeded {CHAIN_TIMEOUT_S:.0f}s and was "
                f"abandoned; the poll will retry") from None
    finally:
        pool.shutdown(wait=False)


def fetch_chain(
    underlying: str,
    min_dte: int,
    max_dte: int,
    asof: date | None = None,
) -> list[Contract]:
    """Pull the chain for one underlying, restricted to a DTE band."""
    asof = asof or date.today()
    req = OptionChainRequest(underlying_symbol=underlying, feed=_feed())
    snapshots = _chain_with_deadline(req)

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
                open_interest=float(getattr(snap, "open_interest", 0) or 0),
                volume=float(getattr(getattr(snap, "daily_bar", None), "volume", 0) or 0),
                delta=float(greeks.delta) if greeks and greeks.delta is not None else None,
                iv=(
                    float(snap.implied_volatility)
                    if getattr(snap, "implied_volatility", None) is not None
                    else None
                ),
            )
        )
    return out


def liquid(contracts: list[Contract], max_rel_spread: float,
           min_open_interest: float = 0.0, min_volume: float = 0.0) -> list[Contract]:
    """Keep only contracts we could realistically get filled on.

    open_interest and volume were configured and documented as gates but no
    code read them, so the universe was wider than the config claimed. They
    are enforced here, and skipped when the feed does not report them rather
    than silently emptying the chain.
    """
    out = []
    for c in contracts:
        if not (c.tradable and c.rel_spread <= max_rel_spread
                and c.bid_size > 0 and c.ask_size > 0):
            continue
        if min_open_interest and c.open_interest and c.open_interest < min_open_interest:
            continue
        if min_volume and c.volume and c.volume < min_volume:
            continue
        out.append(c)
    return out


def implied_spot(contracts: list[Contract]) -> float | None:
    """Underlying price implied by the chain, via put-call parity.

    C - P = S - K, so the strike where call and put mids converge is the
    spot. Free, and it cannot disagree with the quotes the gates are
    already reasoning about, which a separate spot feed could.
    """
    # Parity only holds WITHIN one expiry. Keying on strike alone paired a
    # call from one expiry with a put from another and returned a number that
    # is not a price of anything. Restrict to the nearest expiry present.
    tradable = [c for c in contracts if c.tradable]
    if not tradable:
        return None
    expiry = min(c.expiry for c in tradable)
    calls = {c.strike: c.mid for c in tradable if c.right == "C" and c.expiry == expiry}
    puts = {c.strike: c.mid for c in tradable if c.right == "P" and c.expiry == expiry}
    common = set(calls) & set(puts)
    if not common:
        return None
    k = min(common, key=lambda s: abs(calls[s] - puts[s]))
    return k + calls[k] - puts[k]


def nearest_expiry(contracts: list[Contract]) -> date | None:
    expiries = sorted({c.expiry for c in contracts})
    return expiries[0] if expiries else None
