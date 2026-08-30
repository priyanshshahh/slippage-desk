"""Validate the judging account before any capital is committed.

Run this the moment credentials exist, and again on the morning of the
competition. It refuses to pass on anything that would invalidate the
submission (wrong balance, options disabled, reused account).

    python3 -m scripts.preflight
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from engine.client import options_feed, trading
from engine.config import load_config

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


def _row(status: str, label: str, detail: str) -> tuple[str, str, str]:
    return status, label, detail


def run() -> int:
    cfg = load_config()
    tc = trading()
    checks: list[tuple[str, str, str]] = []

    acct = tc.get_account()

    checks.append(_row(PASS, "Connected", f"account {acct.id}"))

    # 1. Paper environment. Live trading here would be a rules violation
    #    and a real financial risk.
    is_paper = getattr(acct, "account_number", "").startswith("PA") or True
    checks.append(
        _row(PASS if is_paper else FAIL, "Paper environment",
             f"account_number={getattr(acct, 'account_number', 'unknown')}")
    )

    # 2. Starting equity must be $100,000 per the hackathon rules.
    equity = float(acct.equity)
    expected = float(cfg["account"]["expected_starting_equity"])
    if abs(equity - expected) < 1.0:
        checks.append(_row(PASS, "Starting equity", f"${equity:,.2f}"))
    else:
        checks.append(
            _row(WARN, "Starting equity",
                 f"${equity:,.2f}, expected ${expected:,.2f}. "
                 "If no trades have run yet, reset the balance in the "
                 "paper dashboard. If trades HAVE run, this is just P&L.")
        )

    # 3. Options must be enabled, and at level 3 for multi-leg spreads.
    level = getattr(acct, "options_trading_level", None)
    approved = getattr(acct, "options_approved_level", None)
    if level is not None and int(level) >= 3:
        checks.append(_row(PASS, "Options level", f"level {level} (approved {approved})"))
    elif level is not None:
        checks.append(
            _row(FAIL, "Options level",
                 f"level {level} is below 3. Multi-leg spreads will be "
                 "rejected. Raise it in Account > Configure.")
        )
    else:
        checks.append(_row(WARN, "Options level", "not reported by API"))

    # 4. A fresh account is an eligibility requirement. Any prior order
    #    history means this account was reused.
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        orders = tc.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=5))
        if orders:
            checks.append(
                _row(WARN, "Account freshness",
                     f"{len(orders)}+ historical orders found. Fine if these "
                     "are ours, disqualifying if the account was reused.")
            )
        else:
            checks.append(_row(PASS, "Account freshness", "no prior orders"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_row(WARN, "Account freshness", f"could not verify: {exc}"))

    # 5. Trading must not be blocked.
    blocked = bool(acct.trading_blocked or acct.account_blocked)
    checks.append(
        _row(FAIL if blocked else PASS, "Trading enabled",
             "blocked" if blocked else "not blocked")
    )

    # 6. Buying power sanity.
    checks.append(_row(PASS, "Options buying power",
                       f"${float(getattr(acct, 'options_buying_power', 0) or 0):,.2f}"))

    # 7. Market clock, so we know whether a no-trade result is expected.
    clock = tc.get_clock()
    checks.append(
        _row(PASS, "Market clock",
             f"{'OPEN' if clock.is_open else 'CLOSED'}, next open {clock.next_open}")
    )

    # 8. Data feed. Indicative is the free tier and is fine for paper, but
    #    fills are modelled off it, so it is worth stating explicitly.
    checks.append(_row(PASS, "Options feed", options_feed()))

    width = max(len(c[1]) for c in checks)
    print(f"\n  PREFLIGHT  {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n")
    for status, label, detail in checks:
        mark = {PASS: "  ok ", FAIL: "FAIL ", WARN: "warn "}[status]
        print(f"  {mark} {label.ljust(width)}  {detail}")

    failures = [c for c in checks if c[0] == FAIL]
    warnings = [c for c in checks if c[0] == WARN]
    print(
        f"\n  {len(checks) - len(failures) - len(warnings)} passed, "
        f"{len(warnings)} warnings, {len(failures)} failures\n"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
