"""Offline test of the autonomous loop's non-deterministic edges.

smoke_test.py proves the gates. This proves the parts that only show up
once the agent is actually running a position: when it exits, how it picks
up a spread the broker has but the ledger does not, and that a broken
advisor stops trading rather than waving trades through.

No credentials, no network, no market data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from agent import loop, model, positions
from engine.assignment import ExDivCalendar, assignment_gate, detect_assignment
from agent.positions import OpenSpread
from engine.config import load_config
from engine.risk import PortfolioState, evaluate
from engine.strategy import build_candidates
from engine.chain import liquid
from engine import execute
from scripts.smoke_test import synth_chain

ET = ZoneInfo("America/New_York")


def occ(root: str, expiry: date, right: str, strike: float) -> str:
    return f"{root}{expiry:%y%m%d}{right}{int(strike * 1000):08d}"


def sample_spread(expiry: date) -> OpenSpread:
    """Short 635P / long 630P for 0.90 credit. Width 5, so max loss 410."""
    return OpenSpread(
        underlying="SPY",
        kind="put_credit",
        expiry=expiry.isoformat(),
        short_symbol=occ("SPY", expiry, "P", 635),
        long_symbol=occ("SPY", expiry, "P", 630),
        contracts=2,
        entry_credit=0.90,
        max_loss_per_contract=410.0,
        bucket="SPY:1dte:d15:midday",
        opened_at=datetime.now().astimezone().isoformat(),
    )


def test_exit_rules(cfg: dict) -> None:
    print("\n--- exit rules ---")
    tomorrow = date.today() + timedelta(days=1)
    s = sample_spread(tomorrow)
    midday = datetime.now(ET).replace(hour=12, minute=0)

    # Thresholds come from config so the test follows the configuration
    # rather than encoding one moment of it. Entry credit is 0.90.
    take = float(cfg["exit"]["profit_take_pct"])
    stopm = float(cfg["exit"]["stop_loss_multiple"])
    tp = 0.90 * (1 - take)          # buy back at or below this
    sl = 0.90 * stopm               # cut at or above this
    cases = [
        (round(tp - 0.05, 2), "profit_take", f"below the {take:.0%} target"),
        (round(tp, 2),        "profit_take", "exactly at the threshold"),
        (round(tp + 0.05, 2), None,          "not yet at the target"),
        (round((tp + sl) / 2, 2), None,      "losing, but inside the stop"),
        (round(sl, 2),        "stop_loss",   f"{stopm:g}x the credit taken in"),
        (round(sl + 0.7, 2),  "stop_loss",   "well past the stop"),
    ]
    print(f"  (profit target {take:.0%} -> buy back at {tp:.2f}; "
          f"stop {stopm:g}x -> cut at {sl:.2f})")
    for cost, expected, why in cases:
        got = loop._exit_reason(s, cost, cfg, midday)
        status = "ok " if got == expected else "FAIL"
        print(f"  [{status}] cost {cost:.2f} -> {str(got):18s} {why}")
        assert got == expected, f"cost {cost}: expected {expected}, got {got}"

    # Force close fires on expiry day after 15:45 regardless of price.
    today = date.today()
    s_today = sample_spread(today)
    late = datetime.now(ET).replace(hour=15, minute=50)
    early = datetime.now(ET).replace(hour=15, minute=30)

    assert loop._exit_reason(s_today, 0.60, cfg, late) == "force_close_expiring"
    print("  [ok ] 15:50 on expiry day -> force_close_expiring, at any price")
    assert loop._exit_reason(s_today, 0.60, cfg, early) is None
    print("  [ok ] 15:30 on expiry day -> hold, still inside the window")

    # Force close must outrank a stop, so an expiring loser exits on time.
    assert loop._exit_reason(s_today, 9.99, cfg, late) == "force_close_expiring"
    print("  [ok ] expiring and past the stop -> force close wins")


def test_adoption() -> None:
    print("\n--- adopting a spread the broker has and the ledger does not ---")
    expiry = date.today() + timedelta(days=1)
    broker = [
        {"symbol": occ("SPY", expiry, "P", 635), "qty": "3",
         "side": "short", "avg_entry_price": "1.50"},
        {"symbol": occ("SPY", expiry, "P", 630), "qty": "3",
         "side": "long", "avg_entry_price": "0.60"},
        # An equity position must be ignored, not parsed as an option.
        {"symbol": "AAPL", "qty": "100", "side": "long", "avg_entry_price": "220.00"},
    ]

    adopted = loop.adopt_unknown(broker)
    assert len(adopted) == 1, f"expected 1 adopted spread, got {len(adopted)}"
    a = adopted[0]
    print(f"  adopted {a.underlying} {a.kind} {a.contracts}x "
          f"credit {a.entry_credit:.2f} max loss ${a.max_loss_per_contract:.0f}")
    assert a.contracts == 3
    assert abs(a.entry_credit - 0.90) < 1e-9, a.entry_credit
    assert abs(a.max_loss_per_contract - 410.0) < 1e-6, a.max_loss_per_contract
    assert a.kind == "put_credit"
    print("  [ok ] credit is short avg minus long avg, taken from the broker")
    print("  [ok ] equity position ignored")

    # Adopting twice must not double count.
    assert loop.adopt_unknown(broker) == []
    assert len(positions.load()) == 1
    print("  [ok ] second pass adopts nothing, no double count")


def test_reconcile() -> None:
    print("\n--- reconcile drops what the broker no longer holds ---")
    before = positions.load()
    assert before, "expected the adopted spread to still be in the ledger"
    dropped = positions.reconcile(set())
    assert len(dropped) == 1
    assert positions.load() == []
    print(f"  [ok ] {dropped[0].short_symbol} dropped, ledger now empty")


def test_multi_expiry_pairing(cfg: dict) -> None:
    """The bug that shipped: legs paired across different expiries.

    synth_chain() emits a single expiry, so the original smoke test could
    never see this. A real 0-2 DTE band spans several expiries, and pairing
    across them yields a diagonal whose short leg outlives its cover.
    """
    print("\n--- multi-expiry chain: legs must not pair across expiries ---")
    d1 = date.today() + timedelta(days=1)
    d2 = date.today() + timedelta(days=2)
    chain = liquid(synth_chain(spot=640.0, expiry=d1)
                   + synth_chain(spot=640.0, expiry=d2),
                   float(cfg["entry"]["max_rel_spread"]))
    expiries = {c.expiry for c in chain}
    assert len(expiries) == 2, expiries
    print(f"  chain spans {len(expiries)} expiries: {sorted(expiries)}")

    spreads = build_candidates(chain, cfg)
    assert spreads, "expected candidates from a two-expiry chain"
    for sp in spreads:
        assert sp.short_leg.expiry == sp.long_leg.expiry, (
            f"DIAGONAL: short {sp.short_leg.symbol} / long {sp.long_leg.symbol}"
        )
    print(f"  [ok ] all {len(spreads)} candidates have matching leg expiries")

    per_expiry: dict = {}
    for sp in spreads:
        per_expiry[sp.expiry] = per_expiry.get(sp.expiry, 0) + 1
    print(f"  [ok ] candidates built per expiry: {per_expiry}")

    from engine.strategy import Spread
    a = [c for c in chain if c.expiry == d1 and c.right == "C"][5]
    b = [c for c in chain if c.expiry == d2 and c.right == "C"][7]
    bad = Spread(underlying="SPY", kind="call_credit",
                 short_leg=a, long_leg=b, expiry=a.expiry)
    state = PortfolioState(
        equity=100_000, starting_equity=100_000, day_pnl=0.0,
        open_positions=0, open_risk=0.0,
        now_et=datetime.now(ET).replace(hour=11, minute=15),
    )
    d = evaluate(bad, state, cfg)
    assert not d.allowed and "same_expiry" in d.blocked_by, d.blocked_by
    print(f"  [ok ] hand-built diagonal refused: {d.blocked_by}")


def test_assignment_risk(cfg: dict) -> None:
    print("\n--- early-assignment risk ---")
    expiry = date.today() + timedelta(days=2)
    chain = liquid(synth_chain(spot=640.0, expiry=expiry),
                   float(cfg["entry"]["max_rel_spread"]))
    spreads = build_candidates(chain, cfg)
    calls = [s for s in spreads if s.kind == "call_credit"]
    puts = [s for s in spreads if s.kind == "put_credit"]
    assert calls and puts, "need one of each kind"
    call, put = calls[0], puts[0]
    midday = datetime.now(ET).replace(hour=12, minute=0)

    none_cal = ExDivCalendar.empty()
    v = assignment_gate(call, 640.0, none_cal, midday)
    assert v.allowed, v.detail
    print(f"  [ok ] OTM short call, no ex-div -> allow ({v.detail})")

    exdiv = ExDivCalendar({"SPY": [date.today() + timedelta(days=1)]})
    deep = call.short_leg.strike + 5.0
    v = assignment_gate(call, deep, exdiv, midday)
    assert not v.allowed, "ITM short call with ex-div must be refused"
    print(f"  [ok ] ITM short call + ex-div -> BLOCK ({v.detail})")

    v = assignment_gate(call, 640.0, exdiv, midday)
    assert v.allowed, v.detail
    print("  [ok ] OTM short call + ex-div -> allow, strike not ITM")

    near = date.today() + timedelta(days=1)
    chain2 = liquid(synth_chain(spot=640.0, expiry=near),
                    float(cfg["entry"]["max_rel_spread"]))
    put2 = [s for s in build_candidates(chain2, cfg) if s.kind == "put_credit"][0]
    below = put2.short_leg.strike - 5.0
    v = assignment_gate(put2, below, none_cal, midday)
    assert not v.allowed, "ITM short put at 1 DTE must be refused"
    print(f"  [ok ] ITM short put, 1 DTE -> BLOCK ({v.detail})")

    state = PortfolioState(
        equity=100_000, starting_equity=100_000, day_pnl=0.0,
        open_positions=0, open_risk=0.0,
        now_et=datetime.now(ET).replace(hour=11, minute=15),
    )
    blocked = assignment_gate(call, deep, exdiv, midday)
    d = evaluate(call, state, cfg, assignment=blocked)
    assert not d.allowed and d.contracts == 0
    assert "assignment_risk" in d.blocked_by
    print(f"  [ok ] gate folds into evaluate: blocked_by={d.blocked_by}")


def test_assignment_detection() -> None:
    print("\n--- detecting an assignment that already happened ---")
    broker = [
        {"symbol": "SPY260904P00635000", "qty": "1", "side": "short",
         "asset_class": "us_option", "avg_entry_price": "1.50"},
        {"symbol": "SPY", "qty": "100", "side": "short",
         "asset_class": "us_equity", "avg_entry_price": "635.00"},
    ]
    hits = detect_assignment(broker, ["SPY", "QQQ"])
    assert len(hits) == 1, hits
    print(f"  [ok ] {hits[0]}")
    assert detect_assignment([broker[0]], ["SPY", "QQQ"]) == []
    print("  [ok ] options-only book -> no false positive")


def _approved_candidate(cfg: dict):
    chain = liquid(synth_chain(), float(cfg["entry"]["max_rel_spread"]))
    state = PortfolioState(
        equity=100_000, starting_equity=100_000, day_pnl=0.0,
        open_positions=0, open_risk=0.0,
        now_et=datetime.now(ET).replace(hour=11, minute=15),
    )
    for sp in build_candidates(chain, cfg):
        d = evaluate(sp, state, cfg)
        if d.allowed and d.contracts > 0:
            return d, state
    raise AssertionError("no approved candidate to advise on")


def test_advisor_fails_closed(cfg: dict) -> None:
    print("\n--- advisor fail-closed ---")
    decision, state = _approved_candidate(cfg)

    # No provider at all must veto. Patch the resolver rather than the
    # environment, because the CLI is a provider and it is installed here.
    original = model._provider
    model._provider = lambda: None
    try:
        op = model.advise(decision, state, cfg, dte=1)
        assert op.multiplier == 0.0 and op.failed, op
        print(f"  [ok ] no provider -> multiplier {op.multiplier}, '{op.reason}'")
    finally:
        model._provider = original

    # A provider that raises must also veto, not propagate.
    original_cli = model._ask_claude_cli
    model._ask_claude_cli = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        op = model.advise(decision, state, cfg, dte=1)
        assert op.multiplier == 0.0 and op.failed, op
        print(f"  [ok ] provider raises  -> multiplier {op.multiplier}, '{op.reason}'")
    finally:
        model._ask_claude_cli = original_cli

    # Unparseable output must veto rather than crash.
    model._ask_claude_cli = lambda *a, **k: "I think you should probably size down a bit"
    try:
        op = model.advise(decision, state, cfg, dte=1)
        assert op.multiplier == 0.0 and op.failed, op
        print(f"  [ok ] unparseable      -> multiplier {op.multiplier}, '{op.reason}'")
    finally:
        model._ask_claude_cli = original_cli

    # Out-of-range multipliers clamp instead of being trusted.
    model._ask_claude_cli = lambda *a, **k: '{"multiplier": 9.0, "reason": "upsize me"}'
    try:
        op = model.advise(decision, state, cfg, dte=1)
        assert op.multiplier == 1.0, op
        print(f"  [ok ] model asks 9.0x  -> clamped to {op.multiplier}")
    finally:
        model._ask_claude_cli = original_cli

    decision.contracts = 0
    op = model.advise(decision, state, cfg, dte=1)
    assert op.multiplier == 0.0
    print(f"  [ok ] zero-size candidate short-circuits, '{op.reason}'")


def test_advisor_live(cfg: dict) -> None:
    """Exercise the real provider once. Skips cleanly if none is reachable."""
    print("\n--- advisor, live provider ---")
    provider = model._provider()
    if provider is None:
        print("  [skip] no advisor provider reachable")
        return
    print(f"  provider: {provider}")
    decision, state = _approved_candidate(cfg)
    op = model.advise(decision, state, cfg, dte=1)
    assert 0.0 <= op.multiplier <= 1.0, op
    status = "ok " if not op.failed else "warn"
    print(f"  [{status}] multiplier {op.multiplier:.2f}  reason: {op.reason[:70]}")
    if op.failed:
        print("        (advisor unreachable right now; agent would veto, which is correct)")


def test_limit_pricing() -> None:
    print("\n--- execution-quality pricing ---")
    mid, worst = 1.20, 1.00
    prev = None
    for a in (0.0, 0.25, 0.5, 0.75, 1.0):
        limit = execute.limit_for_credit_at(mid, worst, a)
        assert worst - 1e-9 <= limit <= mid + 1e-9, limit
        if prev is not None:
            assert limit <= prev, "more aggressive must never ask for more credit"
        prev = limit
        print(f"  [ok ] aggressiveness {a:.2f} -> ask {limit:.2f}")
    assert execute.limit_for_credit_at(mid, worst, 5.0) == worst
    print("  [ok ] out-of-range aggressiveness clamps to fully crossed")


def main() -> int:
    cfg = load_config()

    # Keep the real ledger untouched.
    with tempfile.TemporaryDirectory() as tmp:
        positions.LEDGER = Path(tmp) / "open_spreads.json"

        test_exit_rules(cfg)
        test_adoption()
        test_reconcile()
        test_multi_expiry_pairing(cfg)
        test_assignment_risk(cfg)
        test_assignment_detection()
        test_advisor_fails_closed(cfg)
        test_advisor_live(cfg)
        test_limit_pricing()

    print("\nALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
