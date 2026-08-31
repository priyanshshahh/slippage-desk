"""Alpaca CLI wrapper.

The hackathon requires the MCP server or the CLI, and the CLI is the better
fit for a long-running agent: it is a single static binary, it emits
structured JSON on every command, and it is cheap enough to call on a 60
second loop without the overhead of an MCP session.

This module is the agent's hands. Account state, positions, the market
clock, and order submission all go through the CLI so the autonomous loop
is reproducible from a terminal, which also makes the demo legible.

Read paths use the CLI. Chain snapshots stay on the Python SDK, because
the SDK returns greeks in one call and the agent needs delta on every
strike to pick the short leg.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from engine.config import ROOT

BIN = ROOT / "bin" / "alpaca"


class CLIError(RuntimeError):
    pass


@dataclass
class CLIResult:
    ok: bool
    data: dict | list | None
    raw: str
    argv: list[str]


def _env() -> dict[str, str]:
    """CLI reads the same credentials the SDK does."""
    env = dict(os.environ)
    env.setdefault("ALPACA_API_KEY", os.getenv("ALPACA_API_KEY", ""))
    env.setdefault("ALPACA_SECRET_KEY", os.getenv("ALPACA_SECRET_KEY", ""))
    # Absence of ALPACA_LIVE_TRADE means paper, which is what we want.
    env.pop("ALPACA_LIVE_TRADE", None)
    return env


def run(*args: str, timeout: int = 30) -> CLIResult:
    """Invoke the CLI and parse its JSON output."""
    if not BIN.exists():
        raise CLIError(f"Alpaca CLI not found at {BIN}")

    # Note: do NOT pass --quiet. It suppresses the CLI's JSON error
    # envelope along with the warnings, which turns every failure into a
    # silent empty response.
    argv = [str(BIN), *args]
    proc = subprocess.run(
        argv, capture_output=True, text=True, timeout=timeout, env=_env()
    )
    # Success goes to stdout, failures go to stderr as a JSON envelope with
    # a non-zero exit code. Both are JSON, so read whichever is populated.
    raw = proc.stdout.strip() or proc.stderr.strip()

    try:
        data = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return CLIResult(False, None, raw, argv)

    # Documented exit codes: 0 success, 1 error, 2 auth failure. Auth is
    # worth naming separately because it means "fix .env", not "retry".
    if proc.returncode == 2:
        return CLIResult(False, data, f"authentication failed: {raw}", argv)

    # The CLI signals API failures with an "error" field.
    if isinstance(data, dict) and data.get("error"):
        return CLIResult(False, data, str(data["error"]), argv)

    return CLIResult(proc.returncode == 0, data, raw, argv)


def account() -> dict:
    r = run("account", "get")
    if not r.ok:
        raise CLIError(f"account get failed: {r.raw}")
    return r.data


def clock() -> dict:
    r = run("clock")
    if not r.ok:
        raise CLIError(f"clock failed: {r.raw}")
    return r.data


def positions() -> list[dict]:
    r = run("position", "list")
    if not r.ok:
        raise CLIError(f"position list failed: {r.raw}")
    return r.data or []


def open_orders() -> list[dict]:
    r = run("order", "list", "--status", "open")
    return r.data or [] if r.ok else []


def submit_mleg(
    legs: list[dict],
    qty: int,
    limit_price: float,
    time_in_force: str = "day",
    dry_run: bool = True,
    client_order_id: str | None = None,
) -> CLIResult:
    """Submit a multi-leg options order through the CLI.

    legs entries look like:
      {"symbol": ..., "ratio_qty": "1", "side": "sell",
       "position_intent": "sell_to_open"}
    """
    args = [
        "order", "submit",
        "--order-class", "mleg",
        "--qty", str(qty),
        "--type", "limit",
        "--limit-price", str(limit_price),
        "--time-in-force", time_in_force,
        "--legs", json.dumps(legs),
    ]
    # Alpaca rejects a duplicate client_order_id, which turns a retried
    # submission into a no-op instead of a second live spread.
    if client_order_id:
        args += ["--client-order-id", client_order_id[:128]]
    if dry_run:
        args.append("--dry-run")
    return run(*args)


def order_get(order_id: str) -> dict | None:
    """Fetch one order by id. Used to read a fill back after submission."""
    r = run("order", "get", "--order-id", order_id)
    return r.data if r.ok and isinstance(r.data, dict) else None


def cancel(order_id: str) -> CLIResult:
    """Cancel a single order, leaving other resting orders alone."""
    return run("order", "cancel", "--order-id", order_id)


def cancel_all() -> CLIResult:
    return run("order", "cancel-all")


def close_position(symbol: str) -> CLIResult:
    """Close one position. The flag is --symbol-or-asset-id, not --symbol.

    Prefer this over close_all(): the probe on 2026-08-31 showed close-all
    flattening only one leg of a two-leg book, leaving the other open.
    """
    return run("position", "close", "--symbol-or-asset-id", symbol)


def close_all() -> CLIResult:
    """Kill switch. Flattens every position."""
    return run("position", "close-all")


def latest_price(symbol: str) -> float | None:
    """Live spot from the stock feed.

    Deriving spot from the option chain via put-call parity is elegant and
    free, but the indicative options feed lags, and the advisor kept
    (correctly) refusing candidates whose delta was inconsistent with the
    real underlying price. The stock feed is fresher.
    """
    r = run("data", "latest-trade", "--symbol", symbol)
    if not r.ok or not isinstance(r.data, dict):
        return None
    # Shape varies: sometimes {"trade": {"p": ...}}, sometimes flat.
    trade = r.data.get("trade", r.data)
    price = trade.get("p") or trade.get("price")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


def corporate_actions(symbols: list[str], start: str, end: str,
                      types: str = "cash_dividend") -> list[dict]:
    """Upcoming corporate actions. Ex-dividend dates drive early assignment."""
    r = run("data", "corporate-actions", "--symbols", ",".join(symbols),
            "--start", start, "--end", end, "--types", types)
    if not r.ok or not r.data:
        return []
    d = r.data
    if isinstance(d, dict):
        # Response nests by action type; flatten whatever came back.
        out: list[dict] = []
        for v in d.values():
            if isinstance(v, list):
                out.extend(v)
        return out
    return d if isinstance(d, list) else []


def calendar(start: str, end: str) -> list[dict]:
    """Trading sessions. Half days close at 13:00, which a hardcoded
    15:45 force-close would sail straight past."""
    r = run("calendar", "--start", start, "--end", end)
    return r.data if r.ok and isinstance(r.data, list) else []


def portfolio_history(period: str = "1W", timeframe: str = "1H") -> dict:
    """Equity curve straight from the broker.

    P&L is a judged criterion, and an equity curve the broker computed is
    worth more than one this repo derived for itself.
    """
    r = run("account", "portfolio", "--period", period, "--timeframe", timeframe)
    return r.data if r.ok and isinstance(r.data, dict) else {}


def activities(activity_types: str = "FILL", date: str | None = None) -> list[dict]:
    """The broker's own fill record. Independently checkable by a judge."""
    args = ["account", "activity", "list", "--activity-types", activity_types]
    if date:
        args += ["--date", date]
    r = run(*args)
    return r.data if r.ok and isinstance(r.data, list) else []


def doctor() -> CLIResult:
    return run("doctor")


def available() -> bool:
    return BIN.exists()
