"""The model layer, which has strictly negative authority.

The advisor is handed a candidate that has ALREADY passed every
deterministic gate and been sized. Its only outputs are a size multiplier
in [0, 1] and a reason. It cannot propose a trade, pick a strike, widen
risk, or reach around a gate, because nothing here returns anything a
caller could act on except a number that gets multiplied into an
already-approved contract count.

Every failure path returns VETO. A timeout, a malformed response, a
missing key, a refusal, a network blip: all of them mean "do not trade".
That makes model failure degrade to trading less, never to trading worse.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

from engine.risk import Decision, PortfolioState

# Adaptive thinking is on by default on the Anthropic path, so max_tokens
# has to leave room for reasoning as well as the (tiny) JSON answer.
MAX_TOKENS = 2000

def _provider() -> str | None:
    """Which advisor backend is reachable. None means fail closed.

    Preference order, cheapest first:

      claude_cli   the Claude Code CLI, driven non-interactively. Runs on an
                   existing Claude subscription, so the agent needs no API
                   credits at all and still gets a frontier model.
      anthropic    the API proper, if a key happens to be present.
      openai_compat  any OpenAI-shaped endpoint (Ollama, Groq, Gemini's
                   compatibility layer) via ADVISOR_BASE_URL.

    The provider changes nothing downstream. Whichever answers, the clamp is
    identical: the model can only shrink or veto.
    """
    if shutil.which("claude"):
        return "claude_cli"
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if os.getenv("ADVISOR_BASE_URL", "").strip():
        return "openai_compat"
    return None

SYSTEM = """You are a risk advisor for an autonomous options income agent.

The agent sells defined-risk credit spreads. A candidate reaches you only
after passing twelve deterministic risk gates and being sized by a fixed
formula. Your job is NOT to find trades. Your job is to catch the things a
static rule cannot see: an unusual quote, a stale-looking chain, an
earnings or macro event the structure implies, a credit that looks too
generous for the delta, concentration the gates measured but did not judge.

You return a size multiplier and a reason.

  1.0  no concern, take the trade as sized
  0.1 to 0.9  proceed smaller, because of a specific concern
  0.0  veto

You cannot increase size. Values above 1.0 are clamped to 1.0. You cannot
change strikes, structure, or any risk limit. If you have no specific
concern, return 1.0 rather than shrinking out of vagueness: unnecessary
timidity has a real cost. Reserve 0.0 for a concrete, nameable problem.

Reason must be one short sentence naming the actual concern.

Respond with a JSON object only, no prose, of exactly this shape:
{"multiplier": <number between 0 and 1>, "reason": "<one short sentence>"}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "multiplier": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["multiplier", "reason"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Opinion:
    multiplier: float
    reason: str
    failed: bool = False


VETO_ON_ERROR = Opinion(0.0, "advisor unavailable, failing closed", failed=True)


def _brief(decision: Decision, state: PortfolioState, dte: int,
           context: str | None = None) -> str:
    """The facts the advisor gets. Deliberately compact and numeric."""
    s = decision.spread
    gates = ", ".join(f"{v.gate}={v.detail}" for v in decision.verdicts)
    return f"""CANDIDATE
  underlying        {s.underlying}
  structure         {s.kind} {s.short_leg.strike:g}/{s.long_leg.strike:g}
  expiry            {s.expiry} ({dte} DTE)
  credit at mid     {s.credit_mid:.2f}
  credit if crossed {s.credit_worst:.2f}
  slippage to cross ${s.slippage_cost:.0f}/contract
  width             {s.width:g}
  max loss          ${s.max_loss:.0f}/contract
  short leg delta   {s.short_delta:.3f}
  short leg quote   {s.short_leg.bid:.2f} x {s.short_leg.ask:.2f}
  long leg quote    {s.long_leg.bid:.2f} x {s.long_leg.ask:.2f}
  implied vol       {s.short_leg.iv if s.short_leg.iv is not None else 'n/a'}
  approved size     {decision.contracts} contracts
                    (${decision.contracts * s.max_loss:.0f} total risk)

PORTFOLIO
  equity            ${state.equity:,.0f} (started ${state.starting_equity:,.0f})
  day P&L           ${state.day_pnl:,.0f}
  open positions    {state.open_positions}
  open risk         ${state.open_risk:,.0f}
  by underlying     {state.positions_by_symbol}
  trades today      {state.trades_today}

GATES ALREADY PASSED
  {gates}
{_context_block(context)}
Return your multiplier and reason."""


def _context_block(context: str | None) -> str:
    """Live market context from the Alpaca MCP server, when available.

    This is the only place model-facing input comes from outside the
    deterministic pipeline. Alpaca's MCP server explicitly tags its own
    output `trust: untrusted_tool_output`, and it is right to: this text is
    interpolated into a prompt.

    The architecture already contains that. Prompt injection here cannot
    create a trade, pick a strike, or widen risk, because the advisor's
    entire output surface is one number clamped to [0, 1] and multiplied
    into a size the deterministic gates already approved. The worst a
    hostile string can achieve is a veto, which is the safe direction.
    Truncated to bound the prompt regardless.
    """
    if not context:
        return "\nMCP RESEARCH\n  unavailable this cycle\n"
    trimmed = context.strip()[:1200]
    return f"\nMCP RESEARCH (live, read-only)\n  {trimmed}\n"


def advise(
    decision: Decision,
    state: PortfolioState,
    cfg: dict,
    dte: int,
    context: str | None = None,
) -> Opinion:
    """Ask the advisor whether to shrink or veto. Never raises."""
    if decision.contracts <= 0:
        return Opinion(0.0, "nothing to advise on, size already zero")

    timeout = float(cfg["llm"].get("timeout_seconds", 20))
    provider = _provider()
    if provider is None:
        return VETO_ON_ERROR

    brief = _brief(decision, state, dte, context)

    try:
        if provider == "claude_cli":
            text = _ask_claude_cli(brief, cfg, timeout)
        elif provider == "anthropic":
            text = _ask_anthropic(brief, cfg, timeout)
        else:
            text = _ask_openai_compat(brief, cfg, timeout)
    except Exception as exc:                      # noqa: BLE001 - all of them are vetoes
        return Opinion(0.0, f"advisor error, failing closed: {type(exc).__name__}", True)

    if text is None:
        return Opinion(0.0, "advisor refused, failing closed", True)

    try:
        data = json.loads(text)
        multiplier = float(data["multiplier"])
        reason = str(data["reason"])[:200]
    except (StopIteration, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return Opinion(0.0, "advisor returned unusable output, failing closed", True)

    if multiplier != multiplier:                  # NaN
        return Opinion(0.0, "advisor returned NaN, failing closed", True)

    # risk.apply_model_opinion clamps again. Doing it here too means the
    # journal records what was actually applied, not what was requested.
    return Opinion(max(0.0, min(1.0, multiplier)), reason)


def _ask_anthropic(brief: str, cfg: dict, timeout: float) -> str | None:
    import anthropic

    client = anthropic.Anthropic()
    # One attempt inside the poll interval. A retry storm would push the
    # decision past the point where the quote it is based on is real.
    resp = client.with_options(timeout=timeout, max_retries=0).messages.create(
        model=cfg["llm"].get("model", "claude-opus-5"),
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        messages=[{"role": "user", "content": brief}],
    )
    if resp.stop_reason == "refusal":
        return None
    return next(b.text for b in resp.content if b.type == "text")


def _ask_claude_cli(brief: str, cfg: dict, timeout: float) -> str | None:
    """Drive the Claude Code CLI non-interactively as the advisor.

    The CLI authenticates against an existing Claude subscription, so the
    whole agent runs without a single API credit. Volume is trivial: the
    advisor is consulted at most once per poll, and only on a candidate that
    has already cleared every deterministic gate.

    Run from a neutral directory so it does not pick up this repo's own
    context, and hand it one self-contained prompt.
    """
    prompt = (
        f"{SYSTEM}\n\n{brief}\n\n"
        "Output the JSON object and nothing else. No preamble, no code fence."
    )
    proc = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=timeout, cwd="/tmp",
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    # Tolerate a fenced block if one slips through; the parser needs raw JSON.
    if out.startswith("```"):
        out = out.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if out.startswith("json"):
            out = out[4:].strip()
    return out or None


def _ask_openai_compat(brief: str, cfg: dict, timeout: float) -> str | None:
    """Any OpenAI-shaped endpoint: Ollama, Groq, Gemini compatibility layer.

    json_object mode plus the schema restated in the prompt, because
    open-weight servers vary in how strictly they honour json_schema.
    """
    from openai import OpenAI

    client = OpenAI(
        base_url=os.environ["ADVISOR_BASE_URL"],
        api_key=os.getenv("ADVISOR_API_KEY", "not-needed"),
        timeout=timeout,
        max_retries=0,
    )
    resp = client.chat.completions.create(
        model=cfg["llm"].get("openai_compat_model", "llama3.1"),
        max_tokens=512,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": brief},
        ],
    )
    return resp.choices[0].message.content
