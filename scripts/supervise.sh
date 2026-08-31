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
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i -w $$ &
  log "caffeinate holding off idle sleep"
fi

log "started, watching the agent"

while true; do
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    sleep 30
    continue
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
