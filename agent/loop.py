"""The autonomous loop.

Wakes on a fixed interval and does three things in a fixed order:

  1. reconcile  what the broker says is open, versus what we think is open
  2. exits      before entries, always, so a stop is never delayed by a scan
  3. entries    one candidate per poll, and only if every gate allows

Exits run first on purpose. If the loop dies partway through a poll, the
worst outcome should be a missed opportunity, never a missed stop.

Everything the agent considers is journaled, including the rejections.
"""
from __future__ import annotations

import argparse
import time
import traceback
from datetime import date, datetime
from zoneinfo import ZoneInfo

from agent import model, positions
from agent.positions import OpenSpread
from engine import assignment, chain, cli, execute, invariants, journal, mcp
from engine.config import load_config
from engine.execution_quality import ExecutionMemory, bucket_key
from engine.risk import PortfolioState, account_gates, apply_model_opinion, evaluate
from engine.strategy import build_candidates


def _now_et(cfg: dict) -> datetime:
    return datetime.now(ZoneInfo(cfg["schedule"]["timezone"]))


def _log(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", flush=True)


# --------------------------------------------------------------------------
# reconciliation
# --------------------------------------------------------------------------

def _option_legs(broker_positions: list[dict]) -> list[tuple[str, float, float]]:
    """(symbol, signed qty, avg entry price) for option legs only."""
    legs = []
    for p in broker_positions:
        sym = p.get("symbol", "")
        if not chain.parse_occ(sym):
            continue
        qty = float(p.get("qty", 0) or 0)
        if str(p.get("side", "")).lower() == "short":
            qty = -abs(qty)
        legs.append((sym, qty, float(p.get("avg_entry_price", 0) or 0)))
    return legs


def _decision_for(short_symbol: str) -> dict | None:
    """The most recent decision that proposed this short leg.

    Adoption learns the credit actually received from the broker. Scoring
    execution quality needs the theoretical it was measured against AND the
    delta band it belongs in, and both only exist in the decision that
    proposed the trade.
    """
    for row in reversed(journal.load()):
        if row.get("short_symbol") == short_symbol:
            return row
    return None


def _mid_for(short_symbol: str) -> float | None:
    row = _decision_for(short_symbol)
    return float(row["credit_mid"]) if row else None


def adopt_unknown(broker_positions: list[dict],
                  memory: ExecutionMemory | None = None) -> list[OpenSpread]:
    """Pick up spreads the broker has but the ledger does not.

    This is what makes an entry order that filled after we stopped waiting
    still get managed. The broker's own average entry prices give us the
    real credit, so an adopted spread gets the same exit treatment as one
    we watched fill.
    """
    known = {s.short_symbol for s in positions.load()}
    shorts, longs = {}, {}

    for sym, qty, avg in _option_legs(broker_positions):
        if qty == 0 or sym in known:
            continue
        root, expiry, right, strike = chain.parse_occ(sym)
        bucket = (root, expiry, right)
        (shorts if qty < 0 else longs).setdefault(bucket, []).append(
            (strike, sym, abs(qty), avg)
        )

    adopted = []
    for key, short_legs in shorts.items():
        root, expiry, right = key
        for strike, sym, qty, avg in short_legs:
            # The cover is the long leg on the same root/expiry/right that
            # is furthest out of the money relative to this short.
            covers = longs.get(key, [])
            if not covers:
                continue
            cover = min(
                covers,
                key=lambda c: abs(abs(c[0] - strike) - 5.0),
            )
            c_strike, c_sym, c_qty, c_avg = cover
            credit = avg - c_avg
            width = abs(strike - c_strike)
            spread = OpenSpread(
                underlying=root,
                kind="call_credit" if right == "C" else "put_credit",
                expiry=expiry.isoformat(),
                short_symbol=sym,
                long_symbol=c_sym,
                contracts=int(min(qty, c_qty)),
                entry_credit=round(credit, 4),
                max_loss_per_contract=round(max(0.0, width - credit) * 100.0, 2),
                bucket="adopted",
                opened_at=datetime.now().astimezone().isoformat(),
            )
            positions.add(spread)
            adopted.append(spread)
            covers.remove(cover)

            # Score the fill. Without this an order that rested and filled
            # later is managed correctly but never scored, and the whole
            # execution-quality loop stays empty precisely when it matters.
            decision = _decision_for(sym)
            mid = float(decision["credit_mid"]) if decision else None
            if memory is not None and mid and credit > 0:
                dte = max(0, (expiry - date.today()).days)
                # Use the delta the gates actually measured. Hardcoding 0.25
                # here filed every adopted fill under a delta band it may not
                # belong to, corrupting the per-bucket capture data that is
                # this project's central claim.
                short_delta = abs(float(decision["short_delta"]))
                key = bucket_key(root, dte, short_delta,
                                 datetime.now(ZoneInfo("America/New_York")))
                spread.bucket = key
                positions.remove(sym)
                positions.add(spread)
                memory.record_submission(key)
                capture = memory.record_fill(key, mid, credit)
                _log(f"  scored adopted fill: captured {capture:.1%} of mid "
                     f"({credit:.2f} vs {mid:.2f}) in {key}")
    return adopted


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def _trades_today(cfg: dict, today: date) -> int:
    """Entries opened today, counted from the BROKER's activity log.

    This was counted from the journal, which undercounts: an order that
    rests and fills on a later poll is adopted from the broker and never
    gets a journal fill row. Measured live on 2026-08-31 the journal read 8
    while the broker had filled 10, so the daily cap was policing a number
    25% below reality.

    Legs of one mleg order share the millisecond prefix of their activity
    id, which is how they are grouped back into trades. Falls back to the
    journal only if the broker cannot be reached, since a cap that fails
    open is worse than one that is slightly stale.
    """
    tz = ZoneInfo(cfg["schedule"]["timezone"])
    try:
        groups: dict[str, list[dict]] = {}
        for a in cli.activities("FILL"):
            raw = str(a.get("transaction_time", "")).replace("Z", "+00:00")
            if not raw:
                continue
            if datetime.fromisoformat(raw).astimezone(tz).date() != today:
                continue
            groups.setdefault(str(a.get("id", "")).split("::")[0], []).append(a)
        # An entry sells a leg to open; a pure close does not.
        return sum(1 for legs in groups.values()
                   if any("sell" in str(x.get("side", "")) for x in legs))
    except Exception:                              # noqa: BLE001
        n = 0
        for row in journal.load():
            if not row.get("allowed") or not row.get("fill"):
                continue
            ts = datetime.fromisoformat(row["ts"]).astimezone(tz).date()
            if ts == today:
                n += 1
        return n


def build_state(cfg: dict, now_et: datetime) -> PortfolioState:
    acct = cli.account()
    clock = cli.clock()
    equity = float(acct.get("equity", 0) or 0)
    last_equity = float(acct.get("last_equity", equity) or equity)

    ledger = positions.load()
    by_symbol: dict[str, int] = {}
    risk_by_symbol: dict[str, float] = {}
    for s in ledger:
        by_symbol[s.underlying] = by_symbol.get(s.underlying, 0) + s.contracts
        risk_by_symbol[s.underlying] = risk_by_symbol.get(s.underlying, 0.0) + s.risk

    return PortfolioState(
        equity=equity,
        starting_equity=float(cfg["account"]["expected_starting_equity"]),
        day_pnl=equity - last_equity,
        # Contracts, not rows. A single row can hold eight contracts, so a
        # cap on rows reads far stronger than it is.
        open_positions=sum(s.contracts for s in ledger),
        open_risk=sum(s.risk for s in ledger),
        positions_by_symbol=by_symbol,
        risk_by_symbol=risk_by_symbol,
        trades_today=_trades_today(cfg, now_et.date()),
        market_open=bool(clock.get("is_open", False)),
        now_et=now_et,
    )


# --------------------------------------------------------------------------
# exits
# --------------------------------------------------------------------------

def _exit_reason(s: OpenSpread, cost_to_close: float, cfg: dict,
                 now_et: datetime) -> str | None:
    ex = cfg["exit"]
    hh, mm = (int(x) for x in ex["force_close_time"].split(":"))
    # A half day closes at 13:00, so a 15:45 force-close never fires on the
    # one session you would least want to be carrying 0DTE into.
    actual = assignment.session_close(now_et.date())
    if actual and (actual[0], actual[1]) < (hh, mm):
        ch, cm = actual
        total = ch * 60 + cm - 15
        hh, mm = total // 60, total % 60
    if s.expiry_date <= now_et.date() and (now_et.hour, now_et.minute) >= (hh, mm):
        return "force_close_expiring"
    if s.entry_credit <= 0:
        return None
    if cost_to_close <= s.entry_credit * (1.0 - float(ex["profit_take_pct"])):
        return "profit_take"
    if cost_to_close >= s.entry_credit * float(ex["stop_loss_multiple"]):
        return "stop_loss"
    return None


def manage_exits(cfg: dict, now_et: datetime, dry_run: bool) -> int:
    ledger = positions.load()
    if not ledger:
        return 0

    # One chain fetch per underlying, reused across every spread on it.
    chains: dict[str, dict[str, chain.Contract]] = {}
    closed = 0

    for s in ledger:
        if s.underlying not in chains:
            dte = max(0, (s.expiry_date - now_et.date()).days)
            try:
                contracts = chain.fetch_chain(s.underlying, 0, max(dte, 2),
                                              asof=now_et.date())
            except Exception as exc:              # noqa: BLE001
                _log(f"  chain fetch failed for {s.underlying}: {exc}")
                continue
            chains[s.underlying] = {c.symbol: c for c in contracts}

        quotes = chains[s.underlying]
        short_q, long_q = quotes.get(s.short_symbol), quotes.get(s.long_symbol)

        if short_q is None or long_q is None:
            # No quote means we cannot price the exit. Only the clock-based
            # force close fires here, and it must actually get out.
            if _exit_reason(s, float("inf"), cfg, now_et) == "force_close_expiring":
                # A vertical can never cost more than its width to buy back,
                # so the width is a limit that fills while still bounded. The
                # old hardcoded 0.05 would not have filled on anything ITM,
                # which is precisely when a force close matters.
                width = abs(s.max_loss_per_contract / 100.0 + s.entry_credit)
                _log(f"  {s.short_symbol}: force close, no quote, "
                     f"limit {width:.2f} (max possible cost)")
                execute.close_spread(s.symbols, s.contracts, width, dry_run=dry_run)
                closed += 1
            continue

        # Buy back the short at its ask, sell the long at its bid. The price
        # we would actually pay, not the flattering mid.
        cost_to_close = short_q.ask - long_q.bid
        reason = _exit_reason(s, cost_to_close, cfg, now_et)
        if not reason:
            continue

        pnl = (s.entry_credit - cost_to_close) * 100.0 * s.contracts
        _log(
            f"  EXIT {reason}: {s.underlying} {s.kind} "
            f"{s.contracts}x  in {s.entry_credit:.2f} out {cost_to_close:.2f} "
            f"P&L ${pnl:+.0f}"
        )
        execute.close_spread(s.symbols, s.contracts, cost_to_close, dry_run=dry_run)
        # Deliberately NOT removing the ledger row here. A close order can
        # rest unfilled or be rejected, and dropping the row on submission
        # makes the agent believe it is flat while the broker still holds the
        # position. reconcile() removes it on the next poll once the broker
        # confirms it is gone, which is the only source of truth for that.
        closed += 1

    return closed


# --------------------------------------------------------------------------
# entries
# --------------------------------------------------------------------------

def scan_entries(cfg: dict, state: PortfolioState, memory: ExecutionMemory,
                 now_et: datetime, dry_run: bool) -> bool:
    """Evaluate every candidate, journal all of them, act on at most one."""
    blocked = [v for v in account_gates(state, cfg) if not v.allowed]
    if blocked:
        _log(f"  no entries: {', '.join(v.gate + ' (' + v.detail + ')' for v in blocked)}")
        return False

    snapshot = {
        "equity": state.equity,
        "day_pnl": state.day_pnl,
        "open_positions": state.open_positions,
        "open_risk": state.open_risk,
        "trades_today": state.trades_today,
    }

    # One corporate-actions call per poll covers the whole universe.
    exdiv = assignment.ExDivCalendar.fetch(cfg["universe"]["symbols"])

    best = None
    for symbol in cfg["universe"]["symbols"]:
        try:
            contracts = chain.fetch_chain(
                symbol, cfg["entry"]["min_dte"], cfg["entry"]["max_dte"],
                asof=now_et.date(),
            )
        except Exception as exc:                  # noqa: BLE001
            _log(f"  chain fetch failed for {symbol}: {exc}")
            continue

        tradable = chain.liquid(contracts, float(cfg["entry"]["max_rel_spread"]))
        # Live spot from the stock feed; parity off the chain is the fallback.
        # The options feed lags, and assignment risk judged against a stale
        # underlying is judged against the wrong number.
        spot = cli.latest_price(symbol) or chain.implied_spot(tradable)
        for spread in build_candidates(tradable, cfg):
            av = (
                assignment.assignment_gate(spread, spot, exdiv, now_et)
                if spot is not None else None
            )
            decision = evaluate(spread, state, cfg, memory, assignment=av)
            journal.record(decision, snapshot)
            if decision.allowed and decision.contracts > 0:
                # Best risk/reward among everything that passed.
                if best is None or spread.credit_to_width > best.spread.credit_to_width:
                    best = decision

    if best is None:
        _log("  no candidate passed every gate")
        return False

    spread = best.spread
    dte = (spread.expiry - now_et.date()).days
    _log(f"  candidate: {spread.describe()} -> {best.contracts}x")

    if cfg["llm"]["enabled"]:
        # One read-only MCP call per cycle, on the winner only. Returns None
        # if the server is unreachable, which costs context and nothing else.
        context = mcp.research(spread.underlying)
        _log(f"  mcp research: {'ok' if context else 'unavailable'}")
        opinion = model.advise(best, state, cfg, dte, context=context)
        best = apply_model_opinion(best, opinion.multiplier, opinion.reason, cfg)
        _log(f"  advisor: x{opinion.multiplier:.2f}  {opinion.reason}")

    if best.contracts <= 0:
        journal.record(best, snapshot)
        _log("  advisor reduced size to zero, standing down")
        return False

    key = bucket_key(spread.underlying, dte, spread.short_delta, now_et)
    # How far to cross is learned per bucket: buckets that rarely fill get a
    # more aggressive limit, buckets that fill readily hold out for mid.
    aggressiveness = memory.aggressiveness(key)
    limit = execute.limit_for_credit_at(
        spread.credit_mid, spread.credit_worst, aggressiveness
    )

    _log(f"  submitting {best.contracts}x at {limit:.2f} "
         f"(mid {spread.credit_mid:.2f}, crossed {spread.credit_worst:.2f}, "
         f"aggressiveness {aggressiveness})")

    memory.record_submission(key)
    fill = execute.submit_credit_spread(spread, best.contracts, limit, dry_run=dry_run)

    journal.record(best, snapshot, fill={
        "order_id": fill.order_id if fill else None,
        "status": fill.status if fill else None,
        "submitted_limit": fill.submitted_limit if fill else None,
        "filled_price": fill.filled_price if fill else None,
        "bucket": key,
        "aggressiveness": aggressiveness,
    })

    if fill and fill.filled_price is not None:
        capture = memory.record_fill(key, spread.credit_mid, abs(fill.filled_price))
        _log(f"  filled at {fill.filled_price:.2f}, capture {capture:.2%}")
        positions.add(OpenSpread(
            underlying=spread.underlying,
            kind=spread.kind,
            expiry=spread.expiry.isoformat(),
            short_symbol=spread.short_leg.symbol,
            long_symbol=spread.long_leg.symbol,
            contracts=best.contracts,
            entry_credit=abs(fill.filled_price),
            max_loss_per_contract=spread.max_loss,
            bucket=key,
            opened_at=datetime.now().astimezone().isoformat(),
            order_id=fill.order_id,
        ))
    elif not dry_run:
        # Resting limit order. If it fills later, the next poll adopts it
        # from the broker with the real average entry prices.
        _log("  order resting, will be adopted on a later poll if it fills")

    return True


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def poll_once(cfg: dict, memory: ExecutionMemory, dry_run: bool) -> None:
    now_et = _now_et(cfg)

    broker = cli.positions()
    legs = _option_legs(broker)
    qty_by_symbol = {sym: int(abs(q)) for sym, q, _ in legs if q < 0}
    for dropped in positions.reconcile({s for s, _, _ in legs}, qty_by_symbol):
        _log(f"  ledger drop: {dropped.short_symbol} no longer held at broker")
    # An equity position can only have arrived by assignment. Say so loudly.
    for hit in assignment.detect_assignment(broker, cfg["universe"]["symbols"]):
        _log(f"  ** ASSIGNED: {hit} - defined risk no longer holds, flatten it")

    for taken in adopt_unknown(broker, memory):
        _log(f"  adopted from broker: {taken.underlying} {taken.kind} "
             f"{taken.contracts}x at {taken.entry_credit:.2f}")

    state = build_state(cfg, now_et)
    _log(
        f"equity ${state.equity:,.0f}  day P&L ${state.day_pnl:+,.0f}  "
        f"open {state.open_positions} (${state.open_risk:,.0f} risk)  "
        f"trades today {state.trades_today}  "
        f"market {'open' if state.market_open else 'closed'}"
    )

    # Check the agent's own books against the broker before acting on them.
    # Every risk bug here has been internal state quietly disagreeing with
    # reality, so this runs on live state rather than waiting for someone to
    # imagine the right fixture.
    violations = invariants.check(positions.load(), legs, state, cfg)
    blocking = [v for v in violations if v.severity == "block"]
    for v in violations:
        _log(f"  ** INVARIANT {v.severity.upper()}: {v.name}: {v.detail}")

    # Exits always run. A broken book is a reason to stop opening risk, never
    # a reason to stop managing what is already open.
    manage_exits(cfg, now_et, dry_run)

    if blocking:
        _log(f"  no entries: {len(blocking)} invariant violation(s) unresolved")
        return

    if state.market_open:
        scan_entries(cfg, state, memory, now_et, dry_run)


def main() -> int:
    ap = argparse.ArgumentParser(description="Defined-risk options income agent")
    ap.add_argument("--live", action="store_true",
                    help="actually submit orders (paper account); default is dry run")
    ap.add_argument("--once", action="store_true", help="single poll, then exit")
    ap.add_argument("--interval", type=int, default=None,
                    help="override poll_seconds from config")
    args = ap.parse_args()

    cfg = load_config()
    dry_run = not args.live
    interval = args.interval or int(cfg["schedule"]["poll_seconds"])
    memory = ExecutionMemory()

    if not cli.available():
        _log("Alpaca CLI not found at bin/alpaca. See README.")
        return 1

    _log(f"starting  mode={'LIVE (paper account)' if args.live else 'DRY RUN'}  "
         f"interval={interval}s")

    while True:
        try:
            poll_once(cfg, memory, dry_run)
        except KeyboardInterrupt:
            _log("stopped")
            return 0
        except Exception:                          # noqa: BLE001
            # One bad poll must not end the run. The next one re-reads all
            # state from the broker, so there is nothing to repair.
            _log("poll failed:")
            traceback.print_exc()

        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
