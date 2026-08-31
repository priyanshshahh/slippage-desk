# lablab.ai submission fields

Paste-ready. Every number marked `<<FILL>>` must come from a real run before
submitting. Do not ship a placeholder.

---

## Project title

**Slippage Desk**

> Rationale: names the thesis, not the category. "Options agent" is what 27
> teams called themselves. Read the Originality rubric: a title that says
> what is different is doing work that the long description otherwise has to.

Alternate if a safer name is wanted: **Capture** or **Fill Quality Desk**.

---

## Short description

*(255 character hard limit)*

```
An autonomous options income agent that measures its own execution quality. It learns what fraction of theoretical credit it actually captures per bucket, and refuses the buckets where it cannot get filled at the price its edge assumed.
```

---

## Long description

*(minimum 100 words)*

```
Ten agents in this hackathon govern an LLM with deterministic risk gates. All of
them measure whether their decisions were right. None of them measure whether
their executions were good.

That matters more than it sounds. A 15-delta credit spread on SPY earns about $35
per contract at a 50% profit take. Crossing the bid/ask on entry and exit costs
$10 to $20 of it. On a four-session horizon, execution slippage is the same order
of magnitude as the entire strategy edge. An agent that picks the right strike and
then hands half its edge to the spread has not made money, it has made work.

Slippage Desk sells short-dated, defined-risk credit spreads on SPY and QQQ behind
twelve deterministic gates. The LLM layer has strictly negative authority: it may
shrink a trade or veto it, and it is structurally incapable of creating one,
widening risk, or overriding a gate. That clamp lives in code, not in a prompt.
When the model is unreachable the desk vetoes rather than trading unsupervised,
so a model failure degrades to "trades less", never to "trades worse".

The part nobody else has: every fill is scored against the mid it was priced at.
The agent keeps a shrunk capture ratio per (underlying, tenor, delta band, time of
day) bucket, refuses buckets that have historically surrendered too much credit,
and uses the same memory to decide how far to cross on the next order. Buckets
that rarely fill lean toward crossing; buckets that fill readily hold out for mid.

Alpaca's three surfaces have deliberately separate jobs. The CLI executes orders
and verifies the book. The Python SDK pulls option chains with greeks in one call.
The MCP server supplies read-only research context to the advisor. Execution never
routes through MCP, because a stdio subprocess must never sit between the agent and
its stops.

"The strategy was profitable" is not a claim four sessions can settle for anyone
here. "The agent measured its own execution and acted on it" is. scripts/proof.py
emits a sha256-stamped record of every fill, the mid it was priced against, the
credit actually received, and every bucket the execution gate refused.
```

---

## Technology tags

`Alpaca` · `Anthropic Claude` · `Claude Code` · `Next.js` · `Vercel`

## Category tags

`Finance` · `Investment` · `Web Application` · `ProjectFromScratch`

---

## Required links

| Field | Value |
| --- | --- |
| Public GitHub repository | `<<FILL>>` |
| Demo application platform | Vercel |
| Application URL | `<<FILL>>` |
| **Alpaca paper account ID** | `<<FILL>>` |

Cover image: PNG or JPG, **16:9**.
Video: MP4, **3 to 5 minutes** (the rubric scores under 3 min as "Limited").
Slides: **PDF**, mandatory.

---

## AI tool disclosure

lablab Code of Conduct clause 13 requires disclosing reliance on third-party AI
tools. State plainly in the README and the submission: **built with Claude Code
(Anthropic).** This is a requirement, not a modesty question.

---

## Social posts (up to 5)

Tag **@lablabai** and **@AlpacaHQ** on X, and lablab.ai and Alpaca on LinkedIn.
Draft copy in `docs/SOCIAL.md`. Worth $500 x 2 in a separate pool that almost
nobody is contesting.

## Pre-submission checklist

- [ ] Root `LICENSE` present and MIT (rules require MIT compliance)
- [ ] `data/` contains real fills, not seeded demo data
- [ ] `proof.json` regenerated from the final run
- [ ] Repo public
- [ ] Vercel demo live and loading without credentials
- [ ] Options Level 3 confirmed on the judging account
- [ ] Submitted well before Fri 11:00 ET (manual submission needs prior approval)
