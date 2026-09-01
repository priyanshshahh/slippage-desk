"""Runtime invariants over the agent's own risk accounting.

Every risk bug this project has hit came from the same place: internal
bookkeeping quietly disagreeing with the broker, and no test noticing
because the fixture could not express the disagreement.

  * The ledger said 1 contract on QQQ 721. The broker held 8.
  * symbol_concentration counted rows, so 8 contracts read as "2/3".
  * Spread legs paired across expiries, because the chain fixture had one.

Tests are necessary and were not sufficient. These run against live state on
every poll, so a disagreement is caught the moment it exists rather than
whenever someone thinks to write the right fixture.

A violation is not an exception. It is logged loudly and, where it touches
sizing, it is corrected from the broker, because the broker is the truth.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Violation:
    name: str
    detail: str
    severity: str          # "block" halts new entries; "warn" is recorded only


def check(ledger, broker_legs, state, cfg) -> list[Violation]:
    """Compare what the agent believes against what the broker reports."""
    out: list[Violation] = []
    short_qty = {sym: int(abs(q)) for sym, q, _ in broker_legs if q < 0}

    # 1. Quantity. This is the one that cost real money.
    for s in ledger:
        actual = short_qty.get(s.short_symbol)
        if actual is None:
            out.append(Violation(
                "ledger_phantom",
                f"{s.short_symbol} is in the ledger but not at the broker",
                "block"))
        elif actual != s.contracts:
            out.append(Violation(
                "ledger_qty_mismatch",
                f"{s.short_symbol}: ledger {s.contracts}x, broker {actual}x",
                "block"))

    # 2. Positions the broker holds that the ledger has never heard of.
    known = {s.short_symbol for s in ledger}
    for sym, qty in short_qty.items():
        if sym not in known:
            out.append(Violation(
                "unledgered_short",
                f"{sym} {qty}x short at the broker, absent from the ledger",
                "block"))

    # 3. Risk arithmetic. state.open_risk drives the portfolio gate, so if it
    #    disagrees with the ledger the gate is protecting a fiction.
    ledger_risk = sum(s.risk for s in ledger)
    if abs(ledger_risk - state.open_risk) > 1.0:
        out.append(Violation(
            "open_risk_mismatch",
            f"state ${state.open_risk:,.0f} vs ledger ${ledger_risk:,.0f}",
            "block"))

    # 4. The portfolio cap must actually hold.
    cap = float(cfg["risk"]["max_portfolio_risk_pct"]) * state.equity
    if ledger_risk > cap * 1.001:
        out.append(Violation(
            "portfolio_cap_breached",
            f"${ledger_risk:,.0f} open against a ${cap:,.0f} cap",
            "block"))

    # 5. Per-underlying concentration, in dollars. Row counts cannot bound it.
    share = float(cfg["risk"].get("max_symbol_risk_share", 0.5))
    for sym, risk in (state.risk_by_symbol or {}).items():
        if risk > cap * share * 1.001:
            out.append(Violation(
                "symbol_cap_breached",
                f"{sym} holds ${risk:,.0f} against a ${cap * share:,.0f} cap",
                "warn"))

    # 6. Leg quantities must match. A partially filled mleg order leaves the
    #    short and long legs at different sizes, and the position stops being
    #    defined-risk the moment they diverge. Not seen live yet, which is
    #    exactly when it is cheap to catch.
    long_qty = {sym: int(abs(q)) for sym, q, _ in broker_legs if q > 0}
    for s_ in ledger:
        ns, nl = short_qty.get(s_.short_symbol), long_qty.get(s_.long_symbol)
        if ns is not None and nl is not None and ns != nl:
            out.append(Violation(
                "leg_qty_mismatch",
                f"{s_.short_symbol} {ns}x vs cover {s_.long_symbol} {nl}x: "
                "partial fill, risk is no longer defined",
                "block"))

    # 7. Every open spread must still be a vertical. A diagonal's short leg
    #    outlives its cover, and defined risk stops being defined.
    long_syms = {sym for sym, q, _ in broker_legs if q > 0}
    for s in ledger:
        if s.long_symbol not in long_syms:
            out.append(Violation(
                "cover_missing",
                f"{s.short_symbol} has no long leg at the broker: naked",
                "block"))

    return out
