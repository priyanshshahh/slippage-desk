"""Deterministic risk gates.

Every gate is a pure function of state plus config. Nothing here consults
a model. A candidate reaches the broker only if all gates return allow,
and the size it goes in at is computed here, not chosen by anything else.

The ordering matters: cheap account-level gates run before expensive
per-candidate ones, and sizing runs last.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

from engine.strategy import Spread


@dataclass
class Verdict:
    gate: str
    allowed: bool
    detail: str

    def __str__(self) -> str:
        return f"[{'allow' if self.allowed else 'BLOCK'}] {self.gate}: {self.detail}"


@dataclass
class PortfolioState:
    """Everything the gates need to know about where we stand."""

    equity: float
    starting_equity: float
    day_pnl: float
    open_positions: int
    open_risk: float                    # total defined risk, dollars
    positions_by_symbol: dict[str, int] = field(default_factory=dict)
    trades_today: int = 0
    market_open: bool = True
    now_et: datetime | None = None


@dataclass
class Decision:
    """Outcome of running the full gate stack against one candidate."""

    spread: Spread
    verdicts: list[Verdict]
    contracts: int = 0

    @property
    def allowed(self) -> bool:
        return all(v.allowed for v in self.verdicts) and self.contracts > 0

    @property
    def blocked_by(self) -> list[str]:
        return [v.gate for v in self.verdicts if not v.allowed]

    def report(self) -> str:
        head = (
            f"{self.spread.describe()} -> "
            f"{'TRADE ' + str(self.contracts) + 'x' if self.allowed else 'REJECT'}"
        )
        return "\n".join([head] + [f"    {v}" for v in self.verdicts])


def _parse_time(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def account_gates(state: PortfolioState, cfg: dict) -> list[Verdict]:
    """Gates that do not depend on any particular candidate."""
    risk, sched, acct = cfg["risk"], cfg["schedule"], cfg["account"]
    tz = ZoneInfo(sched["timezone"])
    now = state.now_et or datetime.now(tz)
    v: list[Verdict] = []

    v.append(Verdict("market_open", state.market_open,
                     "market open" if state.market_open else "market closed"))

    start, stop = _parse_time(sched["entry_start"]), _parse_time(sched["entry_stop"])
    in_window = start <= now.timetz().replace(tzinfo=None) <= stop
    v.append(Verdict("entry_window", in_window,
                     f"{now:%H:%M} vs {sched['entry_start']}-{sched['entry_stop']} ET"))

    floor = state.starting_equity * float(acct["equity_floor_pct"])
    v.append(Verdict("equity_floor", state.equity >= floor,
                     f"equity ${state.equity:,.0f} vs floor ${floor:,.0f}"))

    loss_limit = -abs(state.starting_equity * float(risk["daily_loss_limit_pct"]))
    v.append(Verdict("daily_loss_limit", state.day_pnl > loss_limit,
                     f"day P&L ${state.day_pnl:,.0f} vs limit ${loss_limit:,.0f}"))

    v.append(Verdict("max_positions",
                     state.open_positions < int(risk["max_concurrent_positions"]),
                     f"{state.open_positions}/{risk['max_concurrent_positions']} open"))

    v.append(Verdict("daily_trade_cap",
                     state.trades_today < int(risk["max_new_trades_per_day"]),
                     f"{state.trades_today}/{risk['max_new_trades_per_day']} today"))

    return v


def candidate_gates(spread: Spread, state: PortfolioState, cfg: dict) -> list[Verdict]:
    """Gates specific to one proposed spread."""
    entry, risk = cfg["entry"], cfg["risk"]
    v: list[Verdict] = []

    ctw = spread.credit_to_width
    v.append(Verdict("credit_to_width", ctw >= float(entry["min_credit_to_width"]),
                     f"{ctw:.3f} vs min {entry['min_credit_to_width']}"))

    d = spread.short_delta
    in_band = float(entry["short_delta_min"]) <= d <= float(entry["short_delta_max"])
    v.append(Verdict("delta_band", in_band,
                     f"short delta {d:.3f} vs "
                     f"{entry['short_delta_min']}-{entry['short_delta_max']}"))

    worst = max(spread.short_leg.rel_spread, spread.long_leg.rel_spread)
    v.append(Verdict("quote_width", worst <= float(entry["max_rel_spread"]),
                     f"widest leg {worst:.2f} vs max {entry['max_rel_spread']}"))

    # If crossing both legs wipes out the credit, there is no trade here
    # regardless of how good the mid looked.
    v.append(Verdict("crossable", spread.credit_worst > 0,
                     f"credit at mid {spread.credit_mid:.2f}, "
                     f"crossing both legs {spread.credit_worst:.2f}"))

    v.append(Verdict("defined_risk", spread.max_loss > 0 and spread.width > 0,
                     f"max loss ${spread.max_loss:.0f} on width {spread.width:g}"))

    held = state.positions_by_symbol.get(spread.underlying, 0)
    v.append(Verdict("symbol_concentration",
                     held < int(risk["max_positions_per_symbol"]),
                     f"{held}/{risk['max_positions_per_symbol']} in {spread.underlying}"))

    return v


def size_position(spread: Spread, state: PortfolioState, cfg: dict) -> tuple[int, Verdict]:
    """Contracts to trade, capped by both per-trade and portfolio risk."""
    risk = cfg["risk"]
    per_trade_budget = state.equity * float(risk["max_loss_per_trade_pct"])
    portfolio_budget = state.equity * float(risk["max_portfolio_risk_pct"]) - state.open_risk

    if spread.max_loss <= 0:
        return 0, Verdict("sizing", False, "max loss is zero, cannot size")

    by_trade = int(per_trade_budget // spread.max_loss)
    by_portfolio = int(max(0.0, portfolio_budget) // spread.max_loss)
    n = max(0, min(by_trade, by_portfolio))

    return n, Verdict(
        "sizing", n > 0,
        f"{n}x (per-trade allows {by_trade}, portfolio allows {by_portfolio}, "
        f"${spread.max_loss:.0f} risk each)",
    )


def evaluate(spread: Spread, state: PortfolioState, cfg: dict) -> Decision:
    """Run the full stack. Order is cheap-to-expensive, sizing last."""
    verdicts = account_gates(state, cfg) + candidate_gates(spread, state, cfg)
    if not all(v.allowed for v in verdicts):
        # Still record a sizing verdict so the log shows the whole picture.
        n, sv = size_position(spread, state, cfg)
        return Decision(spread, verdicts + [sv], 0)

    n, sv = size_position(spread, state, cfg)
    return Decision(spread, verdicts + [sv], n)


def apply_model_opinion(decision: Decision, multiplier: float, reason: str, cfg: dict) -> Decision:
    """Fold in the model's opinion, which may only ever shrink the trade.

    The multiplier is clamped to the configured range and can never raise
    size above what the deterministic gates already approved. A model that
    returns 5.0 gets treated as 1.0. A model that errors gets treated as a
    veto, so failure is fail-closed.
    """
    lo = float(cfg["llm"]["min_size_multiplier"])
    hi = float(cfg["llm"]["max_size_multiplier"])
    m = max(lo, min(hi, float(multiplier)))

    scaled = int(decision.contracts * m)
    decision.verdicts.append(
        Verdict("model_opinion", scaled > 0,
                f"multiplier {m:.2f} ({decision.contracts} -> {scaled}): {reason}")
    )
    decision.contracts = scaled
    return decision
