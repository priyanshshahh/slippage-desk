#!/bin/bash
# Keep the trading agent alive for the competition window.
#
# The agent already survives a bad poll: any exception is logged and the next
# poll re-reads all state from the broker. What it does not survive is the
# process dying, which a laptop sleeping, an OOM, or a network stack reset
# can all cause. Over four unattended days that is the likeliest way to end
# up with an empty journal and no P&L.
#
# This restarts it within a minute and records every restart, so the log
# shows honestly whether the run was continuous.
#
#   nohup bash scripts/supervise.sh > logs/supervisor.log 2>&1 &

cd "$(dirname "$0")/.." || exit 1
mkdir -p logs

PY="./.venv/bin/python"
PIDFILE="logs/agent.pid"
RESTARTS=0

log() { echo "$(date '+%Y-%m-%d %H:%M:%S')  supervisor: $*"; }

# caffeinate holds off idle sleep for as long as this supervisor lives. A
# sleeping laptop stops the agent, and no watchdog inside the machine can
# restart a process on a suspended kernel. Closing the lid still sleeps it.
# -d display, -i idle, -m disk, -s system-on-AC, -u user-active.
# -i alone was not enough: the machine still slept 03:32-12:03 on 2026-09-01
# and the agent missed the open plus 2.5 hours of the session.
#
# None of these override a closed lid. On a MacBook, closing the lid sleeps
# the machine regardless, unless pmset disablesleep is set (needs sudo).
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu -w $$ &
  log "caffeinate: display, idle, disk, system and user-active held"
  log "NOTE: a closed lid still sleeps the machine. Leave it open."
fi

log "started, watching the agent"

# A hung agent is alive by every test this loop used to apply. On 2026-09-04
# the chain fetch blocked on a reset connection twice and the process sat
# idle, once for 44 minutes, while kill -0 kept reporting it healthy. A loop
# that is not polling manages no exits, so a stop or the reporting flatten
# would never fire. Liveness is therefore progress in the log, not existence
# of a pid: if agent.log has not been written to in STALE_AFTER seconds, the
# agent is treated as dead and replaced.
STALE_AFTER=300

log_age() {
  [ -f logs/agent.log ] || { echo 999999; return; }
  echo $(( $(date +%s) - $(stat -f %m logs/agent.log) ))
}

while true; do
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    age=$(log_age)
    if [ "$age" -lt "$STALE_AFTER" ]; then
      sleep 30
      continue
    fi
    log "agent pid $(cat "$PIDFILE") alive but silent for ${age}s, restarting"
    kill "$(cat "$PIDFILE")" 2>/dev/null
    sleep 3
    kill -9 "$(cat "$PIDFILE")" 2>/dev/null
    sleep 1
  fi

  RESTARTS=$((RESTARTS + 1))
  log "agent not running, restart #$RESTARTS"
  nohup "$PY" -m agent.loop --live >> logs/agent.log 2>&1 &
  echo $! > "$PIDFILE"
  sleep 15

  if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    log "agent up as pid $(cat "$PIDFILE")"
  else
    # Failing to start is different from crashing later: it usually means
    # credentials or config, which restarting will not fix. Back off so the
    # log stays readable instead of scrolling a restart loop.
    log "agent failed to start, backing off 5 minutes (check logs/agent.log)"
    sleep 300
  fi
done
