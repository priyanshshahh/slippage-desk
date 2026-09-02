# One-page write-up

*Required by the hackathon: AI logic, risk gates, and Alpaca infrastructure.*

## The problem this agent solves

Most autonomous trading agents optimise *what* to trade. Over a four-session
evaluation window that is close to noise: nobody, in this field or outside it,
can establish strategy edge from four days of paper trading.

Something else is measurable in four days, and it is not small. A 0.24-delta
credit spread on SPY collects about $81 per contract on a $5-wide vertical,
and the bid/ask it crosses on entry and again on exit is a material
fraction of that. **Execution
slippage is the same order of magnitude as the entire strategy edge**, and no
other agent in this hackathon measures it.

## AI logic

The model layer has **strictly negative authority**. A candidate reaches it only
after passing fifteen deterministic gates and being sized by a fixed formula. The
model returns one number in `[0, 1]` and a reason. That is the entire interface.

`engine/risk.apply_model_opinion` clamps the value and **multiplies** rather than
assigns, so a model returning 5.0 is treated as 1.0. It cannot select a strike,
change an expiry, widen risk, or reach around a gate, because nothing in the call
path accepts anything else from it.

Every failure path returns veto: timeout, malformed JSON, a refusal stop reason,
NaN, or a missing key. **The field splits here.** Of the 47 other submissions posted
as of September 1, only six say what happens when their model fails at all. This one
refuses: a model failure degrades to "trades less", never to "trades
unsupervised".

The advisor is Claude Opus 5, called with a strict JSON schema, a 90-second
timeout and zero retries, so a slow advisor is treated exactly like a broken one.

## Risk gates

Fifteen deterministic checks run before any order, cheapest first, sizing last.
Each returns a named, logged verdict, and all must allow:

`market_open`, `entry_window`, `equity_floor`, `daily_loss_limit`,
`max_positions`, `daily_trade_cap`, `credit_to_width`, `delta_band`,
`quote_width`, `crossable`, `defined_risk`, `symbol_concentration`, `sizing`.

Every number lives in `config.yaml`, not in code, so the whole risk posture is
auditable in one file.

One calibration worth naming, because it was a real bug caught before it cost a
week: credit-to-width on a vertical tracks the net probability of finishing ITM,
roughly short delta minus long delta. At a 0.15 short leg that is about 0.06 to
0.09. The gate was originally set to 0.15, which demanded roughly double fair
value and blocked 8 of 9 realistic candidates. The agent would have run all week
and traded almost nothing. It is now 0.10, with the reasoning recorded in the
config beside the number.

## The execution-quality loop

This is the part that is ours.

`engine/execution_quality.py` scores every fill against the mid it was priced at,
and keeps a **shrunk** capture ratio per `(underlying, tenor, delta band, time of
day)` bucket. Shrinkage toward 1.0 means one lucky fill cannot make a bucket look
expert; a bucket must earn its reputation over `min_samples_to_veto` fills before
it is allowed to veto anything, so the cold start explores instead of locking
itself out.

The same memory is a control input, not just a report. `aggressiveness(bucket)`
sets how far to cross on the next order: buckets that rarely fill lean toward
crossing, buckets that fill readily hold out for mid. The agent is closing a loop
on its own execution, not just logging it.

## Alpaca infrastructure

Three surfaces, deliberately separate jobs:

| Surface | Job |
| --- | --- |
| **CLI** (`bin/alpaca`) | Execution and book verification. Account, clock, positions, `mleg` order submission, single-order cancel, fill readback. |
| **Python SDK** | Option chain snapshots with greeks and IV in one call, which the delta band gate needs on every strike. |
| **MCP server** | Read-only research context for the advisor, one call per cycle. |

**Execution never routes through MCP,** and that is enforced rather than merely
intended. The server is launched with `ALPACA_TOOLSETS=account,stock-data,
options-data,assets,news`, which omits `trading` entirely, so the MCP process does
not expose an order tool at all. Even if something asked it to trade, there is
nothing there to call. On top of that, a hung stdio subprocess must never be able
to stall an order or a stop, so `engine/mcp.py` fails soft and returns `None`:
losing MCP costs the agent context and never a trade.

Order submission is idempotent. Every `mleg` order carries a `client_order_id`
derived from its legs, size and minute, and Alpaca rejects duplicates, so a
retried poll cannot open a second spread.

Multi-leg `mleg` orders submit each spread atomically, with every short leg
covered inside the same order, which is what Alpaca requires for defined risk.

One honest note on infrastructure: Alpaca's docs are ambiguous about whether a
net-credit `mleg` order takes a positive or negative `limit_price`. The Iron
Condor example on the Level 3 page uses a positive price for a credit structure;
the cost-basis section says a credit becomes negative. Those are probably
different quantities. Rather than guess, `ALPACA_CREDIT_SIGN` has **no default**
and live submission raises `SignNotVerified` until an operator sets it.
`scripts/verify_sign.py` settles it against the broker with one one-lot order.

## What we claim, and what we do not

We do not claim the strategy is profitable. Four sessions cannot establish that
for anyone in this hackathon, and any entrant claiming otherwise is reading noise.

We claim the agent measured its own execution quality and acted on it, and we ship
the evidence: `scripts/proof.py` emits `data/proof.json` with every fill, the mid
it was priced against, the credit actually received, per-bucket capture ratios,
which buckets the execution gate refused, and a sha256 over the payload so the
record cannot be quietly edited after the fact.

**Results from the competition window:**

- Candidates considered: `<<FILL>>`
- Orders filled: `<<FILL>>`
- Aggregate capture ratio: `<<FILL>>`
- Given up to execution: `<<FILL>>`
- Buckets vetoed by the execution gate: `<<FILL>>`
- P&L: `<<FILL>>`

*Built with Claude Code (Anthropic).*
