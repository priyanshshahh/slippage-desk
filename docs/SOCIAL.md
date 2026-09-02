# Social posts

Up to 5 links submitted. Separate prize pool: **$500 x 2 teams**, plus one month
of Algo Trader Plus each. Only a handful of teams are contesting it.

Tag **@lablabai** and **@AlpacaHQ** on X. Tag **lablab.ai** and **Alpaca** on
LinkedIn. Judged on quality *and* engagement.

**Rule: never post a number you cannot reconcile against the account.**
Every figure below was verified on 2026-08-31.

---

## POST 1: the hook. Post this first.

### X, short version (fits 280)

```
I read all 47 submissions in the @AlpacaHQ x @lablabai trading hackathon.

11 describe the same architecture: "LLM proposes, deterministic gates authorize."

All of them measure whether their DECISIONS were right.

None measure whether their EXECUTIONS were good.

That's the whole edge.
```

### X, long version (if you have Premium)

```
I read all 47 submissions in the @AlpacaHQ x @lablabai AI trading hackathon.

11 describe the same architecture:
"LLM proposes, deterministic gates authorize."

All of them measure whether their decisions were right.
None measure whether their executions were good.

On a 4-day horizon that IS the game:

A 0.24-delta credit spread pays $32.43 on a win.
The stop costs $81.09.
Breakeven win rate: 71.4%
Delta-implied OTM rate: 76%

Your entire edge is 4.6 percentage points, worth $5.19 a contract.
Crossing the bid/ask cost $1.78 of that. 34% of the edge.

So I built an agent that scores every fill against the mid it was
priced at, learns its capture ratio per (symbol, tenor, delta,
time-of-day) bucket, and refuses the buckets where it cannot get
filled at the price its edge assumed.

Live right now:
693 candidates considered
428 cleared every risk gate
20 actually traded
97.9% of theoretical credit captured

That last number is verified against Alpaca's own activity log, not
my bookkeeping. Anyone with the account ID can reproduce it.

Most agents optimise WHAT to trade.
This one learns whether it can actually get the price.
```

### LinkedIn version

```
I read all 47 submissions in the Alpaca x lablab.ai AI Trading Agents
Hackathon before writing a line of my pitch.

Ten of them describe the same architecture: an LLM proposes, deterministic
risk gates authorise, the model can never override. It is a good design. It
is also, at this point, the baseline rather than a differentiator.

What struck me is what nobody was measuring.

Every one of those agents measures whether its decisions were right. Not one
measures whether its executions were good.

On a four-session horizon, that distinction is the entire game. A 0.24-delta
defined-risk credit spread pays about $32.43 on a win against a $81.09 stop.
The breakeven win rate is 71.4%. A 0.24 short delta implies a 76% chance of
finishing out of the money. So the edge is 4.6 percentage points, worth
$5.19 a contract, and crossing the bid/ask cost $1.78 of that, or 34%
of the edge.

Put plainly: an agent that picks the right strike and then hands half its
edge to the spread has not made money. It has made work.

So I built one that measures the thing nobody measures. Every fill is scored
against the mid it was priced at. It keeps a capture ratio per (underlying,
tenor, delta band, time of day) bucket, refuses the buckets where it has
historically surrendered too much credit, and uses the same memory to decide
how far to cross on the next order.

Currently live on a paper account: 693 candidates considered, 428 cleared
every risk gate, 20 traded, 97.9% of theoretical credit captured. That capture
figure comes from Alpaca's own activity log rather than my own bookkeeping,
so anyone holding the account ID can reproduce it independently.

Four days cannot prove a strategy is profitable. Anyone claiming otherwise
from this window is reading noise. But four days can prove an agent measured
its own execution and acted on what it found, and that is the claim I am
making.

Built with Claude Code. Repo and live dashboard in comments.

#AlgorithmicTrading #AI #Options #Hackathon
```

**Why this one is first:** it opens with a claim nobody can dismiss (you read
all 27), lands a counterintuitive finding, and every number is reconcilable.
That is what gets reshared in this niche. Progress updates are not.

---

## POST 2: the bug that would have cost the week

```
Nearly shipped an options agent that would have gone naked short.

My chain spanned a 0-2 DTE band. Three expiries.
The code picked the short leg by delta across ALL of them,
then picked the long leg by strike across ALL of them.

Result: short 09/02, long 08/31.

That is not a vertical. It is a diagonal.
When the long leg expires first, the short call is left NAKED.

My test fixture generated one expiry, so it was invisible.

Real chains span several. Check yours.

@AlpacaHQ @lablabai
```

---

## POST 3: the docs contradiction, settled for $1.10

```
Alpaca's docs disagreed with themselves about the credit sign on
multi-leg orders.

Iron Condor example: positive limit_price for a net credit.
Cost-basis section: "a credit becomes -$5".

--dry-run does not help. It prints the request locally, the broker
never sees it.

So I placed one one-lot spread and read the fill back:

sent      +0.79
filled    -0.76

Both passages were right about different things.
SUBMISSION takes positive. REPORTING returns negative.

Cost to settle: $1.10 of simulated money.

@AlpacaHQ
```

---

## POST 4: the advisor earning its place

```
My risk gates approved this trade. The LLM refused it:

"Spot 715.20 sits only 0.8% below the 721 short strike after a 1.2%
down day off a 724 high, and the 0.75 credit on a 5-wide spread does
not pay for a 2-DTE gamma gap back to Friday's range."

The model cannot pick a strike, change an expiry, or increase size.
It can shrink a trade or veto it. That is its entire authority.

Turns out that is enough to be useful.

@AlpacaHQ @lablabai
```

---

## POST 5: the result. Post after the final run.

```
Final numbers from 4 sessions on @AlpacaHQ paper:

<<FILL>> candidates considered
<<FILL>> cleared every risk gate
<<FILL>> traded
<<FILL>>% of theoretical credit captured
<<FILL>> buckets refused for poor fill quality

I am not claiming 4 days proves alpha. It does not, for anyone.

What it proves: the agent measured its own execution to the cent and
refused to trade where it could not get filled.

Repo + live dashboard + account ID below. Check the numbers.

@lablabai
```
