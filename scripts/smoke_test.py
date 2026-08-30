"""Offline test of strategy construction and the risk gates.

Runs with no credentials and no market data, so the deterministic logic can
be validated any time, including weekends.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from engine.chain import Contract, liquid
from engine.config import load_config
from engine.risk import PortfolioState, apply_model_opinion, evaluate
from engine.strategy import build_candidates


def synth_chain(spot: float = 640.0, expiry: date | None = None) -> list[Contract]:
    """A plausible SPY-like 1DTE chain.

    Options are priced as intrinsic plus a time value that peaks at the
    money, and delta magnitude moves the right way for each right: put
    delta grows as strike rises, call delta grows as strike falls.
    """
    import math

    expiry = expiry or date.today() + timedelta(days=1)
    out = []
    for strike in [spot + i * 5 for i in range(-10, 11)]:
        dist = (strike - spot) / spot
        # Time value, a bell curve centred at the money.
        tv = 2.6 * math.exp(-((dist / 0.010) ** 2))
        for right in ("P", "C"):
            intrinsic = max(0.0, strike - spot) if right == "P" else max(0.0, spot - strike)
            mid = max(0.02, intrinsic + tv)
            # Delta via a logistic in distance from the money.
            k = 1.0 / (1.0 + math.exp(-dist / 0.006))
            abs_delta = k if right == "P" else 1.0 - k
            abs_delta = max(0.005, min(0.995, abs_delta))
            out.append(
                Contract(
                    symbol=f"SPY{expiry:%y%m%d}{right}{int(strike * 1000):08d}",
                    underlying="SPY",
                    expiry=expiry,
                    right=right,
                    strike=float(strike),
                    bid=round(max(0.01, mid - 0.03), 2),
                    ask=round(mid + 0.03, 2),
                    bid_size=50,
                    ask_size=50,
                    delta=-abs_delta if right == "P" else abs_delta,
                    iv=0.14,
                )
            )
    return out


def main() -> int:
    cfg = load_config()
    chain = synth_chain()
    print(f"synthetic chain: {len(chain)} contracts")

    kept = liquid(chain, cfg["entry"]["max_rel_spread"])
    print(f"after liquidity filter: {len(kept)}")

    candidates = build_candidates(kept, cfg)
    print(f"candidates built: {len(candidates)}\n")
    assert candidates, "expected at least one credit spread candidate"

    state = PortfolioState(
        equity=100_000.0,
        starting_equity=100_000.0,
        day_pnl=-120.0,
        open_positions=1,
        open_risk=500.0,
        positions_by_symbol={"SPY": 1},
        trades_today=1,
        market_open=True,
        now_et=datetime(2026, 8, 31, 11, 15),
    )

    for c in candidates:
        d = evaluate(c, state, cfg)
        print(d.report(), "\n")

    print("=" * 62)
    print("Now proving the model layer can only ever shrink a trade.\n")
    d = evaluate(candidates[0], state, cfg)
    before = d.contracts
    d = apply_model_opinion(d, multiplier=9.0, reason="model tries to upsize", cfg=cfg)
    print(f"model asked for 9.0x: {before} -> {d.contracts} contracts")
    assert d.contracts <= before, "model must never increase size"

    d2 = evaluate(candidates[0], state, cfg)
    d2 = apply_model_opinion(d2, multiplier=0.0, reason="model vetoes", cfg=cfg)
    print(f"model vetoed:        {before} -> {d2.contracts} contracts")
    assert d2.contracts == 0 and not d2.allowed

    print("\n" + "=" * 62)
    print("Proving the daily loss limit halts trading.\n")
    blown = PortfolioState(
        equity=97_500.0, starting_equity=100_000.0, day_pnl=-2_500.0,
        open_positions=1, open_risk=500.0, positions_by_symbol={"SPY": 1},
        trades_today=1, market_open=True, now_et=datetime(2026, 8, 31, 11, 15),
    )
    d3 = evaluate(candidates[0], blown, cfg)
    print(f"blocked by: {d3.blocked_by}")
    assert "daily_loss_limit" in d3.blocked_by and not d3.allowed

    print("\nALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
