# Social posts

Up to 5 links submitted. Separate prize pool: **$500 x 2 teams**, plus one month
of Algo Trader Plus each. Only a handful of teams are contesting it.

Tag **@lablabai** and **@AlpacaHQ** on X. Tag **lablab.ai** and **Alpaca** on
LinkedIn. Judged on quality *and* engagement, so post the counterintuitive
findings, not progress updates. Nobody engages with "day 2 of building".

---

## Post 1 — the hook (post first, it is the strongest)

> Read all 27 submissions in the @AlpacaHQ x @lablabai trading hackathon.
>
> 10 of them govern an LLM with deterministic risk gates.
>
> Every one measures whether its *decisions* were right.
> Not one measures whether its *executions* were good.
>
> A 15-delta SPY credit spread earns ~$35/contract.
> Crossing the spread costs $10-20 of it.
>
> On a 4-day window, fill quality IS the edge. 🧵

---

## Post 2 — the bug that would have cost the week

> Nearly shipped an agent that would have traded nothing all week.
>
> My gate demanded credit ≥ 15% of spread width.
> But credit/width on a vertical tracks (short delta − long delta).
> At a 0.15 short leg that's ~0.06-0.09.
>
> I was asking the market for 2x fair value.
> 8 of 9 realistic candidates: blocked.
>
> Check your gates against the math they imply.

Attach the pass/blocked table. Concrete, checkable, and it makes people think.

---

## Post 3 — the design disagreement

> Split in the field worth noticing.
>
> When the LLM is unreachable, several agents fall back to trading
> deterministically.
>
> Mine refuses.
>
> Fail-open means a model outage becomes an unsupervised trading session.
> Fail-closed means it trades less.
>
> I'll take less. @AlpacaHQ @lablabai

---

## Post 4 — the receipt

> Shipped a proof artifact instead of a P&L screenshot.
>
> Every fill, the mid it was priced against, the credit actually received,
> per-bucket capture ratios, every bucket the execution gate refused.
> sha256 over the payload.
>
> 4 sessions can't prove a strategy works.
> They can prove an agent measured itself.
>
> [link] @AlpacaHQ

---

## Post 5 — the result (post after the final run)

> Final: aggregate capture <<FILL>>% of theoretical credit.
> <<FILL>> given up to execution across <<FILL>> fills.
> <<FILL>> buckets vetoed for poor fill quality.
>
> The agent found where it couldn't get filled, and stopped going there.
>
> Repo + live demo: [links]
> Built with Claude Code. @AlpacaHQ @lablabai

---

**Rules:** never post an unverified number. Post 5 waits for the real run.
