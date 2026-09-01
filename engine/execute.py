"""Order construction and submission for multi-leg credit spreads.

Alpaca requires every short leg to be covered inside the same mleg order,
which is exactly the shape of a defined-risk vertical, so each spread goes
to the broker as one atomic four- or two-leg package.

SIGN CONVENTION, settled empirically 2026-08-31 against the live broker.

The docs looked contradictory, and both passages turned out to be right
about different things. One real one-lot order resolved it:

    sent      limit_price = +0.79   (positive, a net credit)
    accepted  order 9305549d-...
    filled    filled_avg_price = -0.76

So the two conventions are OPPOSITE and both are correct:

  * SUBMISSION takes a POSITIVE limit price for a net credit. That is what
    the Iron Condor example on the Level 3 page was showing.
  * REPORTING returns filled_avg_price NEGATIVE when credit was received.
    That is what the cost-basis section meant by "a credit becomes -$5".

Hence ALPACA_CREDIT_SIGN=1, and every read of a fill takes abs().

This cost $1.10 of simulated money to establish and it is the difference
between selling a spread and buying one. Re-run scripts/verify_sign.py
--probe if Alpaca ever changes the convention.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

from engine.client import trading
from engine.strategy import Spread

# +1 submits credits as positive limit prices, -1 as negative. There is no
# safe default here, so there is no default: dry runs assume +1 so the
# numbers print, and live submission refuses without an explicit setting.
_RAW_SIGN = os.getenv("ALPACA_CREDIT_SIGN", "").strip()
CREDIT_SIGN = int(_RAW_SIGN) if _RAW_SIGN in ("1", "+1", "-1") else 1
SIGN_IS_EXPLICIT = _RAW_SIGN in ("1", "+1", "-1")


class SignNotVerified(RuntimeError):
    """Raised when a live order is attempted before the sign is settled."""


def _require_explicit_sign() -> None:
    if not SIGN_IS_EXPLICIT:
        raise SignNotVerified(
            "ALPACA_CREDIT_SIGN is not set. The mleg credit sign convention is "
            "ambiguous in Alpaca's docs (see this module's docstring). Run "
            "scripts/verify_sign.py, then set ALPACA_CREDIT_SIGN=1 or -1 in "
            ".env before trading live."
        )


@dataclass
class Fill:
    order_id: str
    status: str
    submitted_limit: float
    filled_price: float | None


def build_legs(spread: Spread) -> list[OptionLegRequest]:
    """Two legs: sell the near strike, buy the far one as the cover."""
    return [
        OptionLegRequest(
            symbol=spread.short_leg.symbol,
            ratio_qty=1,
            side=OrderSide.SELL,
            position_intent=PositionIntent.SELL_TO_OPEN,
        ),
        OptionLegRequest(
            symbol=spread.long_leg.symbol,
            ratio_qty=1,
            side=OrderSide.BUY,
            position_intent=PositionIntent.BUY_TO_OPEN,
        ),
    ]


def limit_for_credit_at(
    credit_mid: float, credit_worst: float, aggressiveness: float
) -> float:
    """The credit to ask for, between mid and fully crossed.

    aggressiveness 0.0 asks for the full mid credit and may never fill.
    1.0 gives up everything down to the price we could cross at right now.
    The execution-quality memory supplies this per bucket, so buckets that
    rarely fill lean toward crossing and buckets that fill readily hold out.

    Returns a positive credit per share. Sign is applied at submission.
    """
    a = max(0.0, min(1.0, aggressiveness))
    return round(credit_mid - a * (credit_mid - credit_worst), 2)


def limit_for_credit(credit: float) -> float:
    """Apply the broker's sign convention to a credit, per share."""
    return round(abs(credit), 2) * CREDIT_SIGN


def client_order_id(spread: Spread, contracts: int) -> str:
    """Stable-ish id so a retried submission cannot open a second spread.

    Alpaca rejects a duplicate client_order_id outright. Keying on the legs
    and the minute means a retry inside the same poll is refused by the
    broker, while a genuine re-entry a minute later is still allowed.
    """
    from datetime import datetime, timezone
    minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    stem = f"{spread.short_leg.symbol}-{spread.long_leg.symbol}-{contracts}-{minute}"
    return f"sd-{uuid.uuid5(uuid.NAMESPACE_URL, stem).hex[:24]}"


def submit_credit_spread(
    spread: Spread,
    contracts: int,
    limit_credit: float,
    dry_run: bool = True,
) -> Fill | None:
    """Send one defined-risk credit spread as a single mleg order."""
    if contracts <= 0:
        return None

    limit_price = limit_for_credit(limit_credit)

    req = LimitOrderRequest(
        qty=str(contracts),
        limit_price=str(limit_price),
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        legs=build_legs(spread),
        client_order_id=client_order_id(spread, contracts),
    )

    if dry_run:
        print(
            f"  DRY RUN  {spread.describe()}  x{contracts}  limit {limit_price}"
        )
        return Fill("dry-run", "not_submitted", limit_price, None)

    _require_explicit_sign()
    order = trading().submit_order(req)
    return Fill(
        order_id=str(order.id),
        status=str(order.status),
        submitted_limit=limit_price,
        filled_price=float(order.filled_avg_price) if order.filled_avg_price else None,
    )


def close_spread(position_symbols: list[str], contracts: int, limit_debit: float,
                 dry_run: bool = True) -> Fill | None:
    """Close an open credit spread by buying it back as one package."""
    legs = [
        OptionLegRequest(
            symbol=sym,
            ratio_qty=1,
            side=OrderSide.BUY if i == 0 else OrderSide.SELL,
            position_intent=(
                PositionIntent.BUY_TO_CLOSE if i == 0 else PositionIntent.SELL_TO_CLOSE
            ),
        )
        for i, sym in enumerate(position_symbols)
    ]
    # Absolute net premium, positive, exactly like the open. Direction comes
    # from the legs (buy_to_close / sell_to_close), not from the sign.
    #
    # This was -CREDIT_SIGN, i.e. negative, which asked the broker to PAY us
    # to buy a spread back. Two close orders sat unfilled for eight minutes on
    # 2026-09-01 while the agent retried and collected 403s, because the
    # position was already committed to them. Closing a credit spread costs a
    # debit; a debit is not a negative credit.
    limit_price = round(abs(limit_debit), 2)

    req = LimitOrderRequest(
        qty=str(contracts),
        limit_price=str(limit_price),
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        legs=legs,
        # Without this a resting close is resubmitted every poll: the exit
        # condition is still true, so the agent fires again and again while
        # the first order sits in the book. Opens have carried an idempotency
        # key since the start; closes were missed.
        client_order_id=client_order_id(
            type("S", (), {"short_leg": type("L", (), {"symbol": position_symbols[0]}),
                           "long_leg": type("L", (), {"symbol": position_symbols[1]})}),
            contracts) + "-c",
    )
    if dry_run:
        print(f"  DRY RUN  close {position_symbols} x{contracts} limit {limit_price}")
        return Fill("dry-run", "not_submitted", limit_price, None)

    _require_explicit_sign()
    order = trading().submit_order(req)
    return Fill(str(order.id), str(order.status), limit_price,
                float(order.filled_avg_price) if order.filled_avg_price else None)
