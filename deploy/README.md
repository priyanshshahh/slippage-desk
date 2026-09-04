# Running the desk unattended

`com.slippagedesk.supervisor.plist` is a macOS LaunchAgent. It keeps
`scripts/supervise.sh` alive, which in turn keeps `agent/loop.py` alive.

    cp deploy/com.slippagedesk.supervisor.plist ~/Library/LaunchAgents/
    launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.slippagedesk.supervisor.plist

    launchctl list | grep slippage        # status: pid, last exit code
    launchctl bootout gui/$UID/com.slippagedesk.supervisor   # stop

## Why the repository is not on the Desktop

macOS TCC refuses launchd access to `~/Desktop`, `~/Documents` and
`~/Downloads`. A LaunchAgent pointed at a project inside any of them exits
126 with "Operation not permitted", which is what happened here. The
repository therefore lives at `~/slippage-desk`, with a symlink left at the
old Desktop path for convenience. Moving it back under one of those folders
will break unattended startup.

## What survives what

| Failure | Recovered by | Typical delay |
| --- | --- | --- |
| Agent crashes | supervisor restarts it | under 60s |
| Agent hangs (no log progress) | supervisor's staleness check | up to 5 min |
| Supervisor is killed | launchd `KeepAlive` | under 60s |
| Machine reboots or you log out and in | launchd `RunAtLoad` | at login |
| Machine sleeps | nothing inside the machine can help | until it wakes |

The last row is the real limit. A sleeping Mac freezes the supervisor too,
so no in-machine watchdog can cover it. For genuinely unattended operation
the machine must stay awake: `sudo pmset -c sleep 0`, mains power, lid open.
