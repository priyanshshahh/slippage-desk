# lablab.ai submission fields

Paste-ready. Every number here is broker-verified and regenerates from
`data/proof.json`. Do not ship a placeholder.

---

## Project title

**Slippage Desk**

> Two words that state the thesis rather than the category. "Slippage" names
> the problem and "Desk" names the thing that runs, so the title does work the
> long description would otherwise have to repeat.

---

## Short description

*(232 / 255 characters)*

```
An options income agent that measures its own execution. It scores every fill against the mid it was priced at, learns what fraction of the credit each bucket really captures, and skips the buckets where the edge dies in the spread.
```

---

## Long description

*(1971 characters, inside the form's 2000 limit. Opens with the arithmetic rather than the architecture, because
the arithmetic is what makes the architecture necessary. Closes on the P&L,
because that is the first thing the rubric scores.)*

```
A defined-risk credit spread is a thin trade. This desk collects about $79 per contract on a $5-wide vertical, and the bid/ask it crosses on entry and exit is a material fraction of that. Execution here is not a rounding error, it is a first-order term.

Slippage is usually handled as a pre-trade filter: reject wide quotes, then assume the fill lands near mid. That never tells you what you actually got. Slippage Desk scores the fill itself, then trades on the answer.

It sells 0 to 2 DTE credit spreads on SPY, QQQ and IWM behind fifteen deterministic gates: delta band, credit-to-width floor, quote width, crossability, same-expiry pairing, defined risk, portfolio and per-symbol caps, position and daily trade caps, equity floor, daily loss limit, an entry window, and an early-assignment check reading live corporate actions.

The advisor's authority is a type signature, not a prompt: it returns a multiplier clamped to [0, 1] plus a veto flag, so it cannot open a trade, widen risk or overturn a gate. Every failure path returns 0.0, so an unreachable model trades less, never worse.

The new part: every fill is scored against the mid it was priced at. The desk holds a shrunk capture ratio per (underlying, tenor, delta band, time of day) bucket, ranks candidates by capture-adjusted credit, and uses that memory to set how far to cross next time.

Alpaca's three surfaces have separate jobs. The CLI submits multi-leg orders and verifies the book. The SDK pulls chains with greeks. The MCP server feeds read-only research to the advisor, launched with trading toolsets stripped so it physically cannot place an order.

Broker-verified, not backtested: 36 spreads across 43 contracts, $3,386 captured of $3,446 theoretical, $60 surrendered to execution, 98.3% capture, 2,368 candidates considered. Result: -$454.08 (-0.45%), with the 2% daily loss limit never reached and defined risk on every position. Every figure regenerates from a sha256-signed artifact.
```

---

## Technology tags

`Alpaca` `Alpaca CLI` `Alpaca MCP` `Python` `Claude` `Options` `Next.js` `DuckDB`

## Category tags

`Trading Agent` `Options` `Risk Management` `Autonomous Agents` `Execution Quality`

---

## Required links

| Field | Value |
| --- | --- |
| Public GitHub repository | `https://github.com/priyanshshahh/slippage-desk` |
| Demo application platform | Vercel |
| Application URL | `https://slippage-desk.vercel.app` |
| **Alpaca paper account ID** | `PA343VC6LL3T` |

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
