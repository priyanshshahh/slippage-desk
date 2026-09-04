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

## Additional information

*(1745 characters, inside the form's 2000 limit.)*

```
How to check any claim in this submission, in about two minutes.

Every figure in the video, deck and write-up is generated from data/proof.json, which scripts/proof.py builds from Alpaca's own activity log and portfolio history. It carries every fill, the mid each was priced against, the credit actually received, per-bucket capture ratios, and a sha256 over the payload. Nothing is transcribed by hand.

Two scripts in the repo enforce that, and both run clean on the committed tree:

  python -m scripts.verify_claims
    compares every number across all ten deliverables against proof.json and exits non-zero on drift.

  python -m scripts.check_submission
    validates the package itself: field lengths, cover ratio, video duration and audio, and that every submitted URL returns 200 with no credentials attached.

On the result. The account finished at $-454.08, -0.45% of $100,000. Four sessions cannot establish whether a strategy is profitable, and this submission does not claim otherwise. What the window does establish is measurable: 2,368 candidates considered, 36 spreads filled across 43 contracts, 98.3% of theoretical credit captured, and $60 surrendered to execution. Every position was defined risk, so maximum loss was known before each order went out. Stops closed the losers near 2x credit rather than at full width, the 2% daily loss limit was never reached, and the portfolio risk ceiling never bound.

Worth opening first: engine/execution_quality.py, the capture-ratio loop that is the original part; engine/risk.py, the fifteen deterministic gates; and data/decisions.jsonl, every candidate considered including the refusals, which are the evidence the risk layer does real work.

Built with Claude Code (Anthropic).
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
