# Video script (4:00 target)

**Format:** MP4. Hard max 5:00. The rubric scores under 3:00 as "Limited", so
4:00 is the safe target. Record the screen at 1920x1080.

**Structure the rubric rewards** (lablab Presentation criteria, 5-Excellent):
problem, solution, value proposition, competitive differentiation, and future
plans. Most entrants skip the last two. Do not.

---

### 0:00–0:30 · The problem, stated as a number

> "A point-two-four delta credit spread on SPY collects about eighty-one dollars
> a contract. A win banks thirty-two of that. The stop costs the whole eighty-one.
> So breakeven is seventy-one point four percent, the delta implies seventy-six,
> and the entire edge is four point six points. Five dollars nineteen a contract.
>
> Crossing the bid-ask cost me a dollar seventy-eight of it. That is thirty-four
> percent of the whole edge, gone to execution.
>
> I read all forty-seven other submissions in this hackathon. Eleven promise
> their model can only veto. Every one measures whether its decisions were right.
> **Not one measures whether its executions were good.**"

*On screen:* the arithmetic, big. $5.19 edge per contract vs $1.78 lost to execution.

**Do not open with architecture.** Most of the field opens with architecture.

---

### 0:30–1:15 · What it does

Dashboard, live. Point at the two tiles nobody else can show:
**Credit captured %** and **Lost to execution $**.

> "Every fill gets scored against the mid it was priced at. The agent keeps a
> capture ratio per bucket: underlying, tenor, delta band, time of day. When a
> bucket has historically given up too much credit, it stops trading that bucket.
> And the same memory decides how far to cross on the next order. Buckets that
> rarely fill lean toward crossing. Buckets that fill easily hold out for mid.
>
> It is closing a loop on its own execution, not just logging it."

---

### 1:15–2:15 · The Brain panel, live

Scroll the chain-of-thought feed. Let a **refusal** land on camera.

> "Fifteen deterministic gates, in the order they ran, with the actual numbers.
> This one stopped on credit-to-width: the market wasn't paying enough for the
> risk, so it declined.
>
> The LLM sits here, and it can do exactly two things: shrink the trade, or veto
> it. It cannot pick a strike, change an expiry, or widen risk. That is enforced
> in code. The clamp multiplies, it never assigns."

**The money line, and the field splits on it:**

> "And when the model is unreachable, this desk *refuses*. Of the 47 other
> submissions here, only six say what happens when their model fails at all.
> I'd rather trade less than trade unsupervised."

---

### 2:15–3:00 · Alpaca, all three surfaces

> "CLI executes the orders and verifies the book. The Python SDK pulls chains
> with greeks in one call. The MCP server feeds read-only research to the advisor.
>
> Execution deliberately never goes through MCP. It's a subprocess over stdio, and
> I'm not putting a subprocess between the agent and its stops."

Show a real `mleg` order going out on the CLI and the fill coming back.

---

### 3:00–3:40 · The evidence

Open `data/proof.json`.

> "I'm not going to claim the strategy is profitable. Four sessions can't
> establish that for anyone here, and anyone claiming it is reading noise.
>
> Here's what I will claim, and here's the file. Every fill, the mid it was priced
> against, the credit actually received, per-bucket capture, every bucket the
> execution gate refused, and a sha256 over the payload so it can't be quietly
> edited later."

Say these out loud, they are the ones in data/proof.json:
**693 considered, 428 cleared the gates, 20 spreads filled across 23 contracts,
$1,906 of credit at mid, $1,865 actually captured, $41 surrendered to execution,
97.9% capture, sha256 over the payload.**

---

### 3:40–4:00 · Where it goes

> "Next is cross-venue routing on the same memory, and per-bucket sizing rather
> than just per-bucket veto. The loop generalises to any strategy that pays a
> spread to get in, which is all of them.
>
> Repo and live demo are linked. Built with Claude Code."

---

## Recording checklist

- [ ] Demo has **real fills**, not seeded data
- [ ] A refusal happens on camera. The refusals are the proof.
- [ ] GitHub URL and demo URL both visible on screen
- [ ] Under 5:00, over 3:00
- [ ] Audio checked before the full take
