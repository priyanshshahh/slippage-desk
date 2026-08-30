# Defined-Risk Options Income Agent

An autonomous options agent for the Alpaca AI Trading Agents Hackathon.
It sells short-dated, defined-risk credit spreads on liquid index ETFs,
behind a deterministic risk layer that a language model can veto but never
overrule.

## The core design claim

Most agentic trading systems put a model in the driver's seat and bolt
safety on afterwards. This one inverts that. Position selection, sizing,
and every abort condition are pure functions of market state and a config
file. The model layer has strictly negative authority: it may shrink a
trade or veto it, and it is structurally incapable of creating a trade,
widening risk, or overriding a gate. That is enforced in code, in
`engine/risk.apply_model_opinion`, which clamps the model's output to
`[0.0, 1.0]` and multiplies rather than assigns.

A model failure therefore degrades to "trades less", never to "trades
worse". Model timeouts and malformed responses are treated as vetoes, so
the failure mode is fail-closed.

## Strategy

Short premium, because the evaluation window is roughly four trading days.
Over that horizon a directional thesis is close to a coin flip, while
selling out-of-the-money premium on a liquid underlying produces many
small, high-probability outcomes. Every position is a defined-risk
vertical, so maximum loss is known and capped before submission.

- Underlyings: SPY and QQQ, chosen for penny-wide quotes and daily expiries
- Structure: put credit spreads, call credit spreads, and iron condors
- Tenor: 0 to 2 days to expiry
- Short leg: 0.10 to 0.22 delta, targeting 0.15
- Exit: 50% of credit captured, or 2x credit as a stop, or forced flat at
  15:45 ET to avoid pin and assignment risk

## Risk gates

Twelve deterministic checks run before any order. Each returns a named,
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
| `sizing` | risk budget permits zero contracts |

Sizing runs last and is capped by both a per-trade budget (0.5% of equity)
and a portfolio budget (3% of equity across all open risk).

## Alpaca infrastructure

- **Trading API** for account state, positions, and the market clock
- **Multi-leg (`mleg`) orders**, so each spread is submitted atomically as
  one package with every short leg covered inside the same order, which is
  what Alpaca requires
- **Option chain snapshots** for quotes, greeks, and implied volatility
- **Alpaca CLI** drives the scheduled autonomous loop
- Paper trading throughout

## Layout

```
config.yaml          every risk number, in one auditable place
engine/chain.py      chain retrieval, OCC parsing, liquidity filtering
engine/strategy.py   credit spread construction
engine/risk.py       deterministic gates, sizing, model clamping
engine/execute.py    mleg order submission
engine/journal.py    append-only decision log, rejections included
scripts/preflight.py account validation before capital is committed
scripts/smoke_test.py offline proof of the gate logic, no credentials needed
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
