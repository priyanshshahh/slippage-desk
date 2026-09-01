"""Alpaca MCP server client, used for read-only research only.

The three Alpaca surfaces in this project have deliberately separate jobs:

    CLI   execution and book verification. The agent's hands.
    SDK   option chains with greeks, in one call. The agent's eyes.
    MCP   read-only research context. The agent's second opinion.

Execution never routes through MCP. That is a safety decision, not an
oversight: the MCP server is a subprocess speaking JSON-RPC over stdio,
and a hung or crashed subprocess must never be able to stall or corrupt an
order path. Every function here fails soft and returns None, so losing MCP
costs the agent context, never a trade or a stop.
"""
from __future__ import annotations

import asyncio
import os
import shutil

# Importing config loads .env as a side effect. Without it this module is
# credential-blind in any process that has not already imported the engine,
# and available() silently returns False instead of erroring.
from engine import config as _config  # noqa: F401
from typing import Any

# Deliberately excludes "trading". See _env().
READ_ONLY_TOOLSETS = "account,stock-data,options-data,assets,news"

SERVER_CMD = "uvx"
SERVER_ARGS = ["alpaca-mcp-server"]
# uvx spawns a fresh server process per call, and cold start alone can take
# 20-40s. 25s silently ate every research call. This is generous on purpose:
# MCP is best-effort context, it runs at most once per poll, and the loop
# sleeps 60s between polls anyway.
TIMEOUT = 50.0


def available() -> bool:
    """MCP needs uvx on PATH and credentials to be worth starting."""
    return bool(
        shutil.which(SERVER_CMD)
        and os.getenv("ALPACA_API_KEY", "").strip()
        and os.getenv("ALPACA_SECRET_KEY", "").strip()
    )


def _env() -> dict[str, str]:
    env = dict(os.environ)
    # Absence of a live flag means paper. Belt and braces: the server is
    # only ever handed paper credentials by this project.
    env["ALPACA_PAPER_TRADE"] = "true"
    env.pop("ALPACA_LIVE_TRADE", None)
    # Enforce read-only at the server, not just by convention in our code.
    # Omitting "trading" means the MCP process does not expose an order tool
    # at all, so research cannot place a trade even if something asked it to.
    env["ALPACA_TOOLSETS"] = READ_ONLY_TOOLSETS
    return env


async def _with_session(fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=SERVER_CMD, args=SERVER_ARGS, env=_env())
    # The server logs rich tracebacks to stderr. Useful when debugging MCP,
    # noise that buries real trading decisions when the loop is running.
    with open(os.devnull, "w") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)


def _run(fn) -> Any | None:
    if not available():
        return None
    try:
        return asyncio.run(asyncio.wait_for(_with_session(fn), timeout=TIMEOUT))
    except Exception:                              # noqa: BLE001 - fail soft, always
        return None


def list_tools() -> list[str] | None:
    """Tool names the server exposes. Used by preflight to prove the link."""
    async def _f(session):
        res = await session.list_tools()
        return [t.name for t in res.tools]
    return _run(_f)


def call(tool: str, **arguments: Any) -> Any | None:
    """Call one read-only MCP tool. Returns None on any failure."""
    async def _f(session):
        res = await session.call_tool(tool, arguments)
        # An error result still carries text content, so without this the
        # error message itself was handed to the advisor as market research
        # and the caller logged "mcp research: ok".
        if getattr(res, "isError", False):
            return None
        out = []
        for block in res.content:
            text = getattr(block, "text", None)
            if text is not None:
                out.append(text)
        return "\n".join(out) if out else None
    return _run(_f)


def research(underlying: str) -> str | None:
    """Best-effort market context for one underlying.

    Tool names differ between MCP server versions, so this discovers what
    is actually exposed rather than assuming a name and failing silently.
    """
    tools = list_tools()
    if not tools:
        return None
    for candidate in ("get_stock_snapshot", "get_stock_latest_quote",
                      "get_snapshot", "get_latest_quote"):
        if candidate not in tools:
            continue
        # These tools take `symbols` (plural). Trying `symbol` first made the
        # server raise a 400 and dump a traceback into the agent's log on
        # every single poll, for a call that then succeeded on the retry.
        got = call(candidate, symbols=underlying)
        if got:
            return got
    return None
