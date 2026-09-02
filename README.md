# Slippage Desk

**The options agent that measures its own execution.**

An autonomous options income agent for the Alpaca AI Trading Agents
Hackathon. It sells short-dated, defined-risk credit spreads on SPY, QQQ and
IWM behind fifteen deterministic gates, and it scores every fill against the
mid it was priced at.

An autonomous options agent for the Alpaca AI Trading Agents Hackathon.
It sells short-dated, defined-risk credit spreads on liquid index ETFs,
behind a deterministic risk layer that a language model can veto but never
overrule.

## The core design claim

Ten other agents in this hackathon govern an LLM with deterministic risk
gates. That idea is now the baseline, not a differentiator, and this
project has it too. It is not the claim.

The claim is this: **on a four-session horizon, execution quality is the
same order of magnitude as the entire strategy edge, and nobody measures
it.**

A 0.24-delta credit spread on SPY collects about $78 per contract on a
$5-wide vertical, and the bid/ask it crosses on entry and again on exit is
a material fraction of that. So an agent that picks the right strike and
then hands the credit back to the spread has not made money, it has made
work. Every agent in this
field optimises *what* to trade. This one also learns *whether it can
actually get filled at the price its edge assumed*.

`engine/execution_quality.py` scores every fill against the mid it was
priced at, keeps a shrunk capture ratio per
`(underlying, tenor, delta band, time of day)` bucket, and refuses buckets
that have historically surrendered too much credit. The same memory sets
how far to cross on the next order in that bucket: buckets that rarely
fill lean toward crossing, buckets that fill readily hold out for mid.

That is a narrower claim than "the strategy was profitable", which four
sessions cannot establish for anyone here. It is also the rare claim that
four sessions *can* settle. `scripts/proof.py` emits `data/proof.json`:
every fill with the mid it was priced against and the credit actually
received, per-bucket capture ratios, which buckets were vetoed, and a
sha256 over the payload so the record cannot be quietly edited afterwards.

### The risk layer, which is table stakes

Position selection, sizing, and every abort condition are pure functions
of market state and a config file. The model layer has strictly negative
authority: it may shrink a trade or veto it, and it is structurally
incapable of creating a trade, widening risk, or overriding a gate. That
is enforced in `engine/risk.apply_model_opinion`, which clamps the model's
output to `[0.0, 1.0]` and multiplies rather than assigns.

One difference worth naming, because the field splits on it: when the
model is unreachable, several of these agents fall back to trading
deterministically. This one **vetoes**. A model failure degrades to
"trades less", never to "trades unsupervised".

## Strategy

Short premium, because the evaluation window is roughly four trading days.
Over that horizon a directional thesis is close to a coin flip, while
selling out-of-the-money premium on a liquid underlying produces many
small, high-probability outcomes. Every position is a defined-risk
vertical, so maximum loss is known and capped before submission.

- Underlyings: SPY and QQQ, chosen for penny-wide quotes and daily expiries
- Structure: put credit spreads, call credit spreads, and iron condors
- Tenor: 0 to 2 days to expiry
- Short leg: 0.18 to 0.30 delta, targeting 0.24
- Exit: 40% of credit captured, or 2x credit as a stop, or forced flat at
  15:45 ET to avoid pin and assignment risk

## Risk gates

Fifteen deterministic checks run before any order. Each returns a named,
logged verdict, and all must allow.

| Gate | Blocks when |
| --- | --- |
| `market_open` | market is closed |
| `entry_window` | outside 10:00 to 15:30 ET |
| `equity_floor` | equity below 90% of starting capital |
| `daily_loss_limit` | day P&L worse than -2% |
| `max_positions` | 6 positions already open |
| `daily_trade_cap` | 4 entries already made today |
| `credit_to_width` | credit below 15% of spread width |
| `delta_band` | short leg outside the delta band |
| `quote_width` | either leg's bid/ask exceeds 35% of mid |
| `crossable` | credit vanishes after crossing both legs |
| `defined_risk` | loss is not bounded |
| `symbol_concentration` | 3 positions already in that underlying |
| `assignment_risk` | short call is ITM with an ex-dividend before expiry, or any short leg is ITM inside 1 DTE |
| `sizing` | risk budget permits zero contracts |

Sizing runs last and is capped by both a per-trade budget (0.5% of equity)
and a portfolio budget (3% of equity across all open risk).

## Alpaca infrastructure

- **Trading API** for account state, positions, and the market clock
- **Multi-leg (`mleg`) orders**, so each spread is submitted atomically as
  one package with every short leg covered inside the same order, which is
  what Alpaca requires
- **Option chain snapshots** for quotes, greeks, and implied volatility
- **Corporate actions API** for ex-dividend dates, which drive early
  assignment on short calls
- **Market calendar** so the forced flatten tracks the real session close,
  including 13:00 half days
- **Account activity log** as the broker's own record of every fill
- **Alpaca CLI** drives the scheduled autonomous loop
- Paper trading throughout

## Layout

```
config.yaml            every risk number, in one auditable place
engine/chain.py        chain retrieval, OCC parsing, liquidity filtering
engine/strategy.py     credit spread construction
engine/risk.py         deterministic gates, sizing, model clamping
engine/execute.py      mleg order submission
engine/journal.py      append-only decision log, rejections included
engine/cli.py          Alpaca CLI wrapper, the agent's hands
agent/loop.py          the autonomous poll loop
agent/model.py         the advisor, which can only shrink or veto
agent/positions.py     ledger of open spreads and their entry credits
dashboard/             read-only Next.js view of the journal
scripts/preflight.py   account validation before capital is committed
scripts/smoke_test.py  offline proof of the gate logic, no credentials
scripts/loop_test.py   offline proof of exits, adoption, and fail-closed
scripts/verify_sign.py settles the mleg credit sign against the broker
scripts/seed_demo_data.py  a demo journal, generated by the real gates
```

## Running the agent

```bash
./.venv/bin/python -m scripts.smoke_test    # gates, offline
./.venv/bin/python -m scripts.loop_test     # loop edges, offline
./.venv/bin/python -m agent.loop --once     # one dry-run poll
./.venv/bin/python -m agent.loop            # dry run, every 60s
./.venv/bin/python -m agent.loop --live     # submits to the paper account
```

Order of operations inside a poll is fixed: reconcile against the broker,
then exits, then at most one entry. Exits run first so that if the process
dies mid-poll the worst case is a missed opportunity, never a missed stop.

A poll that throws is logged and swallowed. The next poll re-reads all
state from the broker, so there is nothing to repair by hand.

### The credit sign is not settled yet

Alpaca's docs disagree with themselves about whether a net-credit mleg
order takes a positive or negative `limit_price`. The Iron Condor example
on the Level 3 Trading page submits a credit structure at `"1.80"`,
positive; the cost-basis section says a credit becomes negative. Those are
probably different quantities, but "probably" is not good enough when the
downside is a spread sold at a price meaning the opposite of what was
intended.

So there is no default. Dry runs assume positive; **live submission raises
`SignNotVerified` until `ALPACA_CREDIT_SIGN` is set explicitly**. Run
`scripts/verify_sign.py` first: it offers the same spread to the broker
twice, both as dry runs, and tells you which one it accepts.

## The dashboard

```bash
cd dashboard && npm run dev      # http://localhost:3000
```

A read-only view of `data/`. It shows what the agent considered, what it
declined and which gate stopped it, and how much of the theoretical credit
each execution bucket actually captured. It reads the journal directly
rather than reimplementing any engine logic, so it cannot disagree with
the agent about what happened.

With no journal yet, seed one from the real gate logic running over a
synthetic chain:

```bash
./.venv/bin/python -m scripts.seed_demo_data
```

## Running it

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env      # then fill in the paper keys

./.venv/bin/python -m scripts.smoke_test   # offline, works any time
./.venv/bin/python -m scripts.preflight    # validates the live account
```

## The decision journal

Every candidate the agent considers is appended to `data/decisions.jsonl`,
including rejections and the exact gate that stopped them. The rejections
are the evidence that the risk layer does real work, which is why they are
recorded as carefully as the fills.
