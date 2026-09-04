"""Generate docs/film.html: a self-driving 4 minute video, ready to screen-record.

There is no narration track, so the film has to carry the argument on screen.
Every scene is timed, captions are burned in, and the live dashboard appears as
a real cross-origin iframe that is panned with a CSS transform (its content
cannot be scripted from a file:// page, but the element itself can be moved).

Numbers come from data/proof.json for the same reason every other deliverable
now does: the video script shipped for a day saying "thirty-five dollars a
contract" and "twenty-seven submissions", spelled out as words so no check
caught it.

    PYTHONPATH=. ./.venv/bin/python scripts/build_film.py
    open docs/film.html   # then record the screen for the printed duration
"""

from __future__ import annotations

import json

from engine.config import ROOT

OUT = ROOT / "docs" / "film.html"
SITE = "https://slippage-desk.vercel.app"
REPO = "https://github.com/priyanshshahh/slippage-desk"


def scenes(p: dict) -> list[dict]:
    t, bv, ec = p["totals"], p["broker_verification"], p["economics"]
    cap = (bv["broker_capture_ratio"] or t["aggregate_capture_ratio"]) * 100
    cost = t["given_up_to_execution_usd"] / ec["contracts"]
    eaten = round(cost / ec["expected_per_contract_usd"] * 100)

    return [
        dict(t=6, kind="title",
             kicker="Alpaca AI Trading Agents Hackathon",
             h="Slippage Desk",
             sub="The options agent that measures its own execution."),

        dict(t=26, kind="stats",
             kicker="The problem, as arithmetic",
             h="A credit spread is a thin trade by construction.",
             rows=[("A 0.24-delta spread collects",
                    f"${ec['credit_per_contract_usd']:.2f}", ""),
                   ("A win banks 40% of it",
                    f"+${ec['win_usd']:.2f}", "ok"),
                   ("The stop costs all of it",
                    f"-${ec['loss_usd']:.2f}", "no"),
                   ("So breakeven is",
                    f"{ec['breakeven_win_rate'] * 100:.1f}%", ""),
                   ("A 0.24 delta implies",
                    f"{ec['delta_implied_otm_rate'] * 100:.0f}% OTM", "")],
             note=f"The entire edge is {ec['edge_points']} percentage points. "
                  f"${ec['expected_per_contract_usd']:.2f} a contract."),

        dict(t=23, kind="punch",
             kicker="Where that edge goes",
             big=f"Crossing the bid/ask cost ${cost:.2f} a contract.",
             accent=f"{eaten}% of the entire edge.",
             note="Execution is not a rounding error here. It is a first-order "
                  "term, and it is the one thing four sessions can actually "
                  "measure."),

        dict(t=23, kind="punch",
             kicker="What usually goes unmeasured",
             big="A strategy log says whether the decision was right.",
             accent="It says nothing about what the fill cost.",
             note="Scoring an execution means comparing it to the mid it was "
                  "priced at, at the moment it comes back from the broker. "
                  "Without that comparison, execution cost never appears as a "
                  "number anyone can act on."),

        dict(t=32, kind="frame", src=SITE, pan=[0, -560],
             kicker="The live desk", cap="Every figure on this page is derived "
             "from the config and from the contracts actually filled. Nothing "
             "is typed by hand."),

        dict(t=30, kind="frame", src=SITE, pan=[-560, -1330],
             kicker="Live evidence",
             cap="Per-bucket capture: underlying, tenor, delta band, time of "
                 "day. Buckets that fill readily hold out for mid. Buckets "
                 "that do not, pay up or get skipped."),

        dict(t=32, kind="stats",
             kicker="Fifteen deterministic gates",
             h="The model cannot open a trade.",
             rows=[("Advisor returns", "multiplier [0,1] + veto", ""),
                   ("It can shrink or refuse", "nothing else", "ok"),
                   ("Every failure path returns", "0.0", "no"),
                   ("Model unreachable means", "trade less, never worse", "")],
             note="The clamp is a type signature, not a prompt instruction. "
                  "The failure path is part of the design: timeout, malformed "
                  "JSON, NaN and refusal all return the same veto."),

        dict(t=26, kind="stats",
             kicker="Alpaca, all three surfaces",
             h="Separate jobs, on purpose.",
             rows=[("CLI", "submits mleg orders, verifies the book", ""),
                   ("Python SDK", "pulls chains with greeks", ""),
                   ("MCP server", "read-only research for the advisor", "")],
             note="MCP is launched with the trading toolsets stripped, so "
                  "research physically cannot place an order. Execution never "
                  "goes through a subprocess."),

        dict(t=30, kind="stats",
             kicker="The evidence, not a backtest",
             h="Sourced from Alpaca's own activity log.",
             rows=[("Candidates considered", f"{t['candidates_considered']:,}", ""),
                   ("Spreads filled", f"{bv['paired_spreads']}", ""),
                   ("Credit at mid", f"${t['theoretical_credit_usd']:,.0f}", ""),
                   ("Actually captured", f"${t['captured_credit_usd']:,.0f}", "ok"),
                   ("Surrendered to execution", f"${t['given_up_to_execution_usd']:,.0f}", "no"),
                   ("Capture ratio", f"{cap:.1f}%", "ok")],
             note=f"sha256 {p['sha256'][:32]} over the payload, so it cannot "
                  f"be quietly edited later."),

        dict(t=16, kind="punch",
             kicker="What this does not claim",
             big="Four sessions cannot establish that a strategy is profitable.",
             accent="For anyone in this hackathon.",
             note="What four sessions can establish is that an agent measured "
                  "its own execution and acted on it. That is the claim, and "
                  "the file above is the receipt."),

        dict(t=18, kind="end",
             h="Slippage Desk",
             sub="Next: cross-venue routing on the same memory, and per-bucket "
                 "sizing rather than per-bucket veto.",
             links=[SITE, REPO, "paper account PA343VC6LL3T"]),
    ]


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#09090b;height:100%;overflow:hidden;
  font:16px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif;color:#fafafa}
#stage{position:fixed;left:50%;top:50%;width:1920px;height:1080px;transform-origin:50% 50%}
.s{position:absolute;inset:0;padding:96px 120px;display:flex;
   flex-direction:column;justify-content:center;opacity:0;
   transition:opacity .7s ease}
.s.on{opacity:1}
.kicker{font:17px/1 ui-monospace,Menlo,monospace;letter-spacing:.24em;
  text-transform:uppercase;color:#8b8b94;margin-bottom:34px}
h1{font-size:132px;line-height:.97;letter-spacing:-.035em}
h2{font-size:80px;line-height:1.06;letter-spacing:-.025em;max-width:22ch}
.sub{font-size:40px;color:#d4d4d8;margin-top:30px;max-width:34ch}
.big{font-size:88px;line-height:1.08;letter-spacing:-.03em;max-width:24ch}
.accent{color:#fbbf24}
.note{font-size:31px;color:#a1a1aa;margin-top:40px;max-width:58ch;line-height:1.5}
table{margin-top:48px;border-collapse:collapse;width:100%;max-width:1500px}
td{padding:22px 0;border-bottom:1px solid #27272a;font-size:36px}
td:last-child{text-align:right;font-family:ui-monospace,Menlo,monospace;
  font-size:38px;letter-spacing:-.01em}
.ok{color:#4ade80}.no{color:#fbbf24}
.frame{position:absolute;inset:0;overflow:hidden;background:#09090b}
.zoom{position:absolute;top:0;left:0;width:1240px;height:2600px;
  transform:scale(1.549);transform-origin:0 0}
.frame iframe{position:absolute;top:0;left:0;width:1240px;height:2600px;
  border:0;transition:transform 40s linear}
.capbar{position:absolute;left:0;right:0;bottom:0;padding:42px 120px 48px;
  background:linear-gradient(transparent,rgba(9,9,11,.93) 32%);
  font-size:34px;line-height:1.4;color:#e4e4e7}
.capbar b{color:#8b8b94;font:15px/1 ui-monospace,Menlo,monospace;
  letter-spacing:.24em;text-transform:uppercase;display:block;margin-bottom:14px}
.links{margin-top:52px;font-family:ui-monospace,Menlo,monospace;font-size:32px;
  color:#8b8b94;line-height:2}
#bar{position:fixed;left:0;bottom:0;height:3px;background:#4ade80;width:0;z-index:9}
"""

JS = """
const S=window.__S,stage=document.getElementById('stage'),bar=document.getElementById('bar');
function fit(){const k=Math.min(innerWidth/1920,innerHeight/1080);
  stage.style.transform=`translate(-50%,-50%) scale(${k})`;}
fit();addEventListener('resize',fit);
const total=S.reduce((a,s)=>a+s.t,0);
let i=0,elapsed=0;
function show(){
  if(i>0)stage.children[i-1].classList.remove('on');
  if(i>=S.length){bar.style.width='100%';return;}
  const el=stage.children[i];el.classList.add('on');
  const f=el.querySelector('iframe');
  if(f&&S[i].pan){f.style.transform=`translateY(${S[i].pan[0]}px)`;
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      f.style.transitionDuration=(S[i].t-2)+'s';
      f.style.transform=`translateY(${S[i].pan[1]}px)`;}));}
  const d=S[i].t*1000;elapsed+=S[i].t;i++;
  bar.style.transition=`width ${S[i-1].t}s linear`;
  bar.style.width=(elapsed/total*100)+'%';
  setTimeout(show,d);
}
// Give the iframes a moment to paint before the clock starts.
setTimeout(show,1200);
"""


def render(s: dict) -> str:
    k = f'<div class="kicker">{s["kicker"]}</div>' if s.get("kicker") else ""
    if s["kind"] == "title":
        return f'{k}<h1>{s["h"]}</h1><div class="sub">{s["sub"]}</div>'
    if s["kind"] == "end":
        links = "<br>".join(s["links"])
        return (f'<h1>{s["h"]}</h1><div class="sub">{s["sub"]}</div>'
                f'<div class="links">{links}</div>')
    if s["kind"] == "punch":
        return (f'{k}<div class="big">{s["big"]}<br>'
                f'<span class="accent">{s["accent"]}</span></div>'
                f'<div class="note">{s["note"]}</div>')
    if s["kind"] == "stats":
        rows = "".join(
            f'<tr><td>{a}</td><td class="{c}">{b}</td></tr>' for a, b, c in s["rows"]
        )
        return (f'{k}<h2>{s["h"]}</h2><table>{rows}</table>'
                f'<div class="note">{s["note"]}</div>')
    if s["kind"] == "frame":
        return (f'<div class="frame"><div class="zoom">'
                f'<iframe src="{s["src"]}" scrolling="no"></iframe></div>'
                f'<div class="capbar"><b>{s["kicker"]}</b>{s["cap"]}</div></div>')
    raise ValueError(s["kind"])


def main() -> int:
    proof = json.loads((ROOT / "data" / "proof.json").read_text())
    S = scenes(proof)
    body = "".join(
        f'<section class="s"{"" if s["kind"] != "frame" else " style=padding:0"}>'
        f"{render(s)}</section>"
        for s in S
    )
    meta = json.dumps([{"t": s["t"], "pan": s.get("pan")} for s in S])
    OUT.write_text(
        f"<!doctype html><meta charset=utf-8><title>Slippage Desk film</title>"
        f"<style>{CSS}</style><div id=stage>{body}</div><div id=bar></div>"
        f"<script>window.__S={meta};{JS}</script>"
    )
    runtime = sum(s["t"] for s in S)
    print(f"film written: {OUT}")
    print(f"  scenes   {len(S)}")
    print(f"  runtime  {runtime}s  ({runtime // 60}:{runtime % 60:02d})")
    print(f"  record   screencapture -V {runtime + 4} out.mp4")
    if not 180 < runtime < 300:
        print(f"  ! runtime {runtime}s is outside the 3:00-5:00 rubric window")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
