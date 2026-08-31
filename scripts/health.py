"""One-screen health report. Run it before the open, or any time.

Answers the questions that matter after an unattended stretch: did the agent
survive the night, did it keep trading, is the book what we think it is, and
did anything get assigned.

    python -m scripts.health
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from agent import positions
from engine import cli, journal
from engine.assignment import detect_assignment
from engine.config import ROOT, load_config

ET = ZoneInfo("America/New_York")


def alive(pidfile: Path) -> tuple[bool, str]:
    try:
        pid = int(pidfile.read_text().strip())
    except (OSError, ValueError):
        return False, "no pidfile"
    ok = subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0
    if not ok:
        return False, f"pid {pid} is gone"
    et = subprocess.run(["ps", "-p", str(pid), "-o", "etime="],
                        capture_output=True, text=True).stdout.strip()
    return True, f"pid {pid}, up {et}"


def main() -> int:
    cfg = load_config()
    now = datetime.now(ET)
    problems: list[str] = []

    print(f"\n  SLIPPAGE DESK  {now:%a %d %b %H:%M} ET\n")

    for label, pf in (("supervisor", ROOT / "logs/supervisor.pid"),
                      ("agent", ROOT / "logs/agent.pid")):
        ok, detail = alive(pf)
        print(f"  {'ok ' if ok else 'DOWN'}  {label:12s} {detail}")
        if not ok:
            problems.append(f"{label} is not running")

    restarts = 0
    sup = ROOT / "logs/supervisor.log"
    if sup.exists():
        restarts = sup.read_text().count("restart #")
    print(f"        restarts     {restarts}"
          + ("  (a restart is fine; many means something is wrong)"
             if restarts > 2 else ""))

    try:
        acct = cli.account()
        clock = cli.clock()
        eq, last = float(acct["equity"]), float(acct["last_equity"])
        print(f"\n  ok    equity       ${eq:,.2f}   day P&L ${eq - last:+,.2f}")
        print(f"  ok    market       {'OPEN' if clock.get('is_open') else 'closed'}"
              f"   next open {str(clock.get('next_open', ''))[:16]}")
        floor = float(cfg["account"]["expected_starting_equity"]) * float(
            cfg["account"]["equity_floor_pct"])
        if eq < floor:
            problems.append(f"equity ${eq:,.0f} is below the ${floor:,.0f} floor")
    except Exception as exc:                       # noqa: BLE001
        print(f"  DOWN  broker       {type(exc).__name__}: {exc}")
        problems.append("cannot reach the broker")
        acct = None

    if acct is not None:
        broker = cli.positions()
        ledger = positions.load()
        print(f"\n  ok    broker legs  {len(broker)}")
        print(f"  ok    ledger       {len(ledger)} spread(s), "
              f"${sum(s.risk for s in ledger):,.0f} risk")
        for s in ledger:
            print(f"          {s.underlying} {s.kind} {s.contracts}x "
                  f"exp {s.expiry} in at {s.entry_credit:.2f}")
        # An options-only agent cannot open an equity position.
        for hit in detect_assignment(broker, cfg["universe"]["symbols"]):
            print(f"  !!!!  ASSIGNED     {hit}")
            problems.append(f"assignment: {hit}")

    rows = journal.load()
    if rows:
        last_ts = datetime.fromisoformat(rows[-1]["ts"]).astimezone(ET)
        age = datetime.now(timezone.utc) - datetime.fromisoformat(rows[-1]["ts"])
        s = journal.summary()
        print(f"\n  ok    journal      {s['considered']} considered, "
              f"{s['approved']} approved, {s['traded']} traded")
        print(f"        last entry   {last_ts:%H:%M} ET "
              f"({age.total_seconds() / 60:.0f} min ago)")
        # Stale only matters if the agent SHOULD be evaluating. Once the
        # daily cap is reached or the entry window closes it stops before
        # touching a chain, so silence is the gates working, not a fault.
        capped = s["traded"] >= int(cfg["risk"]["max_new_trades_per_day"])
        stop_h, stop_m = (int(x) for x in cfg["schedule"]["entry_stop"].split(":"))
        in_window = (now.hour, now.minute) < (stop_h, stop_m)
        start_h, start_m = (int(x) for x in cfg["schedule"]["entry_start"].split(":"))
        in_window = in_window and (now.hour, now.minute) >= (start_h, start_m)

        if capped:
            print(f"        quiet        daily cap reached "
                  f"({s['traded']}/{cfg['risk']['max_new_trades_per_day']}), "
                  "not evaluating. Expected.")
        elif not in_window:
            print("        quiet        outside the entry window. Expected.")
        elif acct and cli.clock().get("is_open") and age > timedelta(minutes=10):
            problems.append(f"journal is {age.total_seconds() / 60:.0f} min stale "
                            "while the market is open and the agent should be "
                            "evaluating")

    proof = ROOT / "data" / "proof.json"
    if proof.exists():
        p = json.loads(proof.read_text())
        bv, t = p["broker_verification"], p["totals"]
        cap = bv["broker_capture_ratio"]
        print(f"\n  ok    capture      {cap:.1%}" if cap else "\n  --    capture      no fills yet")
        print(f"        given up     ${t['given_up_to_execution_usd']:,.2f} to execution")

    print()
    if problems:
        print(f"  {len(problems)} PROBLEM(S):")
        for p_ in problems:
            print(f"    - {p_}")
        print("\n  Restart:  nohup bash scripts/supervise.sh > logs/supervisor.log 2>&1 &")
        return 1
    print("  All clear.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
