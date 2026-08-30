"""Order construction and submission for multi-leg credit spreads.

Alpaca requires every short leg to be covered inside the same mleg order,
which is exactly the shape of a defined-risk vertical, so each spread goes
to the broker as one atomic four- or two-leg package.

SIGN CONVENTION, unresolved until verified live:
Alpaca's SDK reference and support pages state that for order_class=mleg a
positive limit_price is a net debit and a negative one is a net credit,
while one docs example shows a credit strategy with a positive price. The
sign is therefore a config value, not a hardcoded assumption, and
scripts/verify_sign.py settles it with a single one-lot order before any
size is put at risk.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

from engine.client import trading
from engine.strategy import Spread

# -1 means credits are submitted as negative limit prices.
CREDIT_SIGN = int(os.getenv("ALPACA_CREDIT_SIGN", "-1"))


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


def limit_for_credit(credit: float, aggressiveness: float = 0.5) -> float:
    """Net limit price for a credit order.

    aggressiveness 0.0 asks for the full mid credit and may never fill.
    1.0 crosses fully to the worst crossable price. 0.5 splits the
    difference, which is the usual place to rest a spread order.
    """
    return round(abs(credit), 2) * CREDIT_SIGN


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
    )

    if dry_run:
        print(
            f"  DRY RUN  {spread.describe()}  x{contracts}  limit {limit_price}"
        )
        return Fill("dry-run", "not_submitted", limit_price, None)

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
    limit_price = round(abs(limit_debit), 2) * (-CREDIT_SIGN)

    req = LimitOrderRequest(
        qty=str(contracts),
        limit_price=str(limit_price),
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        legs=legs,
    )
    if dry_run:
        print(f"  DRY RUN  close {position_symbols} x{contracts} limit {limit_price}")
        return Fill("dry-run", "not_submitted", limit_price, None)

    order = trading().submit_order(req)
    return Fill(str(order.id), str(order.status), limit_price,
                float(order.filled_avg_price) if order.filled_avg_price else None)
