"""Generate a journal to develop and demo the dashboard against.

These are not invented rows. Every decision here is produced by the real
engine.risk.evaluate() running over a synthetic chain, under a range of
portfolio states chosen to exercise each gate. What you see in the
dashboard is the actual gate logic talking, on made-up quotes.

Refuses to touch a journal that already has real entries in it.
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from engine import journal
from engine.chain import liquid
from engine.config import load_config
from engine.execution_quality import ExecutionMemory, bucket_key
from engine.risk import PortfolioState, apply_model_opinion, evaluate
from engine.strategy import build_candidates
from scripts.smoke_test import synth_chain

ET = ZoneInfo("America/New_York")

# Each scenario is a portfolio state that should trip a different gate,
# so the dashboard shows the risk layer doing visibly different work.
SCENARIOS = [
    ("healthy account, mid-session", dict(
        equity=100_000, day_pnl=-120, open_positions=1, open_risk=410,
        positions_by_symbol={"SPY": 1}, trades_today=1, hour=11)),
    ("position limit reached", dict(
        equity=101_200, day_pnl=1_200, open_positions=6, open_risk=2_400,
        positions_by_symbol={"SPY": 3, "QQQ": 3}, trades_today=3, hour=12)),
    ("concentrated in SPY", dict(
        equity=100_400, day_pnl=400, open_positions=3, open_risk=1_230,
        positions_by_symbol={"SPY": 3}, trades_today=3, hour=13)),
    ("daily loss limit breached", dict(
        equity=97_600, day_pnl=-2_400, open_positions=2, open_risk=820,
        positions_by_symbol={"SPY": 1, "QQQ": 1}, trades_today=2, hour=14)),
    ("daily trade cap hit", dict(
        equity=100_800, day_pnl=800, open_positions=2, open_risk=820,
        positions_by_symbol={"SPY": 1, "QQQ": 1}, trades_today=4, hour=14)),
    ("after the entry window", dict(
        equity=100_150, day_pnl=150, open_positions=2, open_risk=820,
        positions_by_symbol={"SPY": 2}, trades_today=2, hour=15, minute=45)),
    ("portfolio risk budget nearly full", dict(
        equity=100_000, day_pnl=0, open_positions=5, open_risk=2_900,
        positions_by_symbol={"SPY": 2, "QQQ": 3}, trades_today=3, hour=10)),
]


def main() -> int:
    force = "--force" in sys.argv
    existing = journal.load()
    if existing and not force:
        print(f"{journal.JOURNAL} already has {len(existing)} rows.")
        print("Refusing to overwrite. Pass --force if this is demo data.")
        return 1

    if force and journal.JOURNAL.exists():
        journal.JOURNAL.unlink()

    cfg = load_config()
    random.seed(7)
    memory = ExecutionMemory()
    written = 0
    base = datetime.now(timezone.utc) - timedelta(days=3)

    for day in range(4):
        for label, sc in SCENARIOS:
            now_et = datetime.now(ET).replace(
                hour=sc["hour"], minute=sc.get("minute", 15),
                second=0, microsecond=0,
            ) - timedelta(days=3 - day)
            # Real chains are struck on round numbers, so the demo is too.
            spot = 640.0 + round(random.uniform(-6, 6))
            chain = liquid(
                synth_chain(spot=spot, expiry=now_et.date() + timedelta(days=1)),
                float(cfg["entry"]["max_rel_spread"]),
            )
            state = PortfolioState(
                equity=sc["equity"],
                starting_equity=100_000,
                day_pnl=sc["day_pnl"],
                open_positions=sc["open_positions"],
                open_risk=sc["open_risk"],
                positions_by_symbol=dict(sc["positions_by_symbol"]),
                trades_today=sc["trades_today"],
                market_open=True,
                now_et=now_et,
            )
            snapshot = {
                "equity": state.equity, "day_pnl": state.day_pnl,
                "open_positions": state.open_positions,
                "open_risk": state.open_risk,
                "trades_today": state.trades_today,
                "scenario": label,
            }

            for spread in build_candidates(chain, cfg):
                decision = evaluate(spread, state, cfg, memory)
                fill = None

                if decision.allowed and decision.contracts > 0:
                    # The advisor shrinks or vetoes roughly a third of the time,
                    # which is what the clamp is there to make safe.
                    roll = random.random()
                    mult = 1.0 if roll < 0.66 else (0.5 if roll < 0.9 else 0.0)
                    reason = {
                        1.0: "no concern, structure and quotes look normal",
                        0.5: "credit looks rich for this delta, taking half size",
                        0.0: "quote width inconsistent with the rest of the chain",
                    }[mult]
                    decision = apply_model_opinion(decision, mult, reason, cfg)

                    if decision.contracts > 0:
                        dte = (spread.expiry - now_et.date()).days
                        key = bucket_key(spread.underlying, dte,
                                         spread.short_delta, now_et)
                        memory.record_submission(key)
                        # Fills land between the crossable price and mid.
                        got = spread.credit_worst + random.uniform(0, 1) * (
                            spread.credit_mid - spread.credit_worst)
                        capture = memory.record_fill(key, spread.credit_mid, got)
                        fill = {
                            "order_id": f"demo-{written:04d}",
                            "status": "filled",
                            "submitted_limit": round(got, 2),
                            "filled_price": round(got, 2),
                            "bucket": key,
                            "capture": round(capture, 4),
                        }

                journal.record(decision, snapshot, fill=fill,
                               ts=now_et.astimezone(timezone.utc))
                written += 1

    summary = journal.summary()
    print(f"wrote {written} decisions to {journal.JOURNAL}")
    print(f"  considered {summary['considered']}, "
          f"traded {summary['traded']}, rejected {summary['rejected']}")
    print("  rejections by gate:")
    for gate, n in summary["rejections_by_gate"].items():
        print(f"    {gate:24s} {n}")
    print(f"\nexecution-quality buckets: {len(memory.report())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
