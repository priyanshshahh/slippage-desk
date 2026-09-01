"""Settle the mleg credit sign convention against the broker.

Alpaca's docs are ambiguous about whether a net-credit multi-leg order
takes a positive or negative limit_price. See engine/execute.py's
docstring for the two conflicting passages.

WHAT DOES NOT WORK, and why this script is shaped the way it is:

The CLI's --dry-run flag is documented as "Print the request body without
submitting". It is a local pretty-printer. The request never leaves the
machine, the broker never sees it, and it will happily "accept" both signs
because it is not validating anything. Any probe built on --dry-run proves
nothing about the convention.

There is no server-side validation endpoint that prices an mleg order
without placing it. So the only thing that actually settles this is one
real order, read back from the broker.

That is what --probe does: ONE contract, on the paper account, then it
reads the fill and immediately closes the position. Max loss on a single
defined-risk spread is the width minus the credit, roughly $400 on a $5
wide SPY spread, in simulated money. That is the cheapest honest answer
available.

    python -m scripts.verify_sign            # inspect both request bodies
    python -m scripts.verify_sign --probe    # place one real one-lot order
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date

from engine import chain, cli
from engine.config import load_config
from engine.strategy import build_candidates


def legs_for(spread) -> list[dict]:
    return [
        {"symbol": spread.short_leg.symbol, "ratio_qty": "1",
         "side": "sell", "position_intent": "sell_to_open"},
        {"symbol": spread.long_leg.symbol, "ratio_qty": "1",
         "side": "buy", "position_intent": "buy_to_open"},
    ]


def pick_candidate(cfg: dict):
    for symbol in cfg["universe"]["symbols"]:
        contracts = chain.fetch_chain(
            symbol, cfg["entry"]["min_dte"], cfg["entry"]["max_dte"],
            asof=date.today(),
        )
        tradable = chain.liquid(contracts, float(cfg["entry"]["max_rel_spread"]))
        candidates = build_candidates(tradable, cfg)
        if candidates:
            return candidates[0]
    return None


def show_bodies(spread, credit: float) -> None:
    """Print what each sign would send. Local only, nothing is submitted."""
    print("These are the request bodies the two conventions would produce.")
    print("--dry-run prints locally; the broker is NOT consulted here.\n")
    for label, limit in (("POSITIVE", credit), ("NEGATIVE", -credit)):
        r = cli.submit_mleg(legs_for(spread), qty=1, limit_price=limit, dry_run=True)
        body = json.dumps(r.data, indent=2) if r.data else r.raw
        print(f"  {label}  limit_price={limit:+.2f}")
        for line in str(body).splitlines():
            print(f"      {line}")
        print()


def probe(spread, credit: float, cfg: dict) -> int:
    """Place one real one-lot order and read the sign off the fill."""
    sign = 1 if "--negative" not in sys.argv else -1
    limit = credit * sign

    print(f"Placing ONE contract at limit_price={limit:+.2f} on the paper account.")
    print(f"  {spread.describe()}")
    print(f"  worst case on this spread: ${spread.max_loss:.0f}, simulated money\n")

    r = cli.submit_mleg(legs_for(spread), qty=1, limit_price=limit, dry_run=False)
    if not r.ok:
        print(f"REJECTED: {r.raw}\n")
        print("A rejection is itself informative. If it names the price or the")
        print("order direction, the other sign is the right one. Re-run with")
        print("--probe --negative to try the opposite.")
        return 1

    order_id = (r.data or {}).get("id") if isinstance(r.data, dict) else None
    print(f"ACCEPTED: order {order_id}\n")
    if not order_id:
        print("No order id returned; check the account manually.")
        return 1

    for _ in range(20):
        time.sleep(3)
        o = cli.order_get(str(order_id))
        if not o:
            continue
        status = str(o.get("status", ""))
        filled = o.get("filled_avg_price")
        print(f"  status={status} filled_avg_price={filled}")
        if status in ("filled", "canceled", "rejected", "expired"):
            break

    o = cli.order_get(str(order_id)) or {}
    filled = o.get("filled_avg_price")
    if filled is None:
        print("\nStill unfilled. Cancelling so it does not rest into the session.")
        cli.cancel(str(order_id))
        print("Re-run closer to the middle of the session for a faster fill.")
        return 2

    filled = float(filled)
    print(f"\nFilled at {filled:+.4f}")
    print("=" * 66)
    if (filled < 0) == (sign < 0):
        print(f"The broker echoed the sign we sent ({sign:+d}).")
    else:
        print(f"The broker returned the OPPOSITE sign to what we sent ({sign:+d}).")
    print()
    print("Now confirm the cash moved the right way: a credit spread should")
    print("have INCREASED buying power. Check the account, then set")
    print(f"    ALPACA_CREDIT_SIGN={sign if filled else 1}")
    print("in .env only if it did. If the account was debited, the convention")
    print("is the opposite of what was just sent.")
    print()
    print("Closing the test position now.")
    # close_all flattened only one leg of a two-leg book during this very
    # probe on 2026-08-31, leaving a naked long. Close each leg explicitly and
    # check the result rather than assuming.
    for sym in (spread.short_leg.symbol, spread.long_leg.symbol):
        r = cli.close_position(sym)
        print(f"  close {sym}: {'ok' if r.ok else 'FAILED ' + str(r.raw)[:80]}")
    left = [p for p in cli.positions()
            if p.get("symbol") in (spread.short_leg.symbol, spread.long_leg.symbol)]
    if left:
        print(f"  WARNING: {len(left)} leg(s) still open, close them by hand")
    return 0


def main() -> int:
    cfg = load_config()
    if not cli.available():
        print("Alpaca CLI not found at bin/alpaca.")
        return 1

    spread = pick_candidate(cfg)
    if spread is None:
        print("No candidate available. Run this during market hours.")
        return 1

    credit = round(abs(spread.credit_mid), 2)
    print(f"Candidate: {spread.describe()}")
    print(f"Net credit at mid: {credit:.2f}\n")

    if "--probe" not in sys.argv:
        show_bodies(spread, credit)
        print("=" * 66)
        print("Nothing above touched the broker. To actually settle the sign:")
        print("    python -m scripts.verify_sign --probe")
        print("which places ONE contract and closes it immediately.")
        return 0

    return probe(spread, credit, cfg)


if __name__ == "__main__":
    sys.exit(main())
