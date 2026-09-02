"use client";

import { useCallback, useEffect, useState } from "react";
import type { Decision } from "@/lib/data";

// Plain rows computed on the server. Importing anything value-shaped from
// lib/data here drags node:fs/promises into the browser bundle and the build
// fails with a Turbopack chunking error.
type BucketRow = { key: string; capture: number };

type Props = {
  considered: number;
  approved: number;
  capture: number | null;
  givenUp: number;
  fills: number;
  sha: string;
  refusal: Decision | null;
  executed: Decision | null;
  buckets: BucketRow[];
};

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

export default function DemoDeck(p: Props) {
  const [i, setI] = useState(0);

  const slides = buildSlides(p);
  const next = useCallback(() => setI((v) => Math.min(v + 1, slides.length - 1)), [slides.length]);
  const prev = useCallback(() => setI((v) => Math.max(v - 1, 0)), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "ArrowRight" || e.key === "Enter") {
        e.preventDefault();
        next();
      } else if (e.key === "ArrowLeft" || e.key === "Backspace") {
        e.preventDefault();
        prev();
      } else if (e.key === "Home") setI(0);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev]);

  return (
    <div
      onClick={next}
      className="flex min-h-screen cursor-pointer select-none flex-col justify-center px-[8vw] py-[8vh]"
    >
      {slides[i]}

      <div className="pointer-events-none fixed inset-x-0 bottom-6 flex items-center justify-between px-[8vw] font-mono text-xs text-muted">
        <span>{i === 0 ? "space / click to advance · ← to go back" : ""}</span>
        <span className="tabular-nums">
          {i + 1} / {slides.length}
        </span>
      </div>
    </div>
  );
}

function Kicker({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-6 font-mono text-sm uppercase tracking-[0.2em] text-muted">
      {children}
    </div>
  );
}

function Big({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[clamp(2rem,5vw,4rem)] font-semibold leading-[1.05] tracking-tight">
      {children}
    </h2>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-8 max-w-4xl text-[clamp(1rem,1.6vw,1.5rem)] leading-relaxed text-foreground/80">
      {children}
    </p>
  );
}

function buildSlides(p: Props) {
  const gates = p.refusal?.verdicts ?? [];
  const stopped = gates.find((v) => !v.allowed);

  return [
    // 1: the hook, not the architecture
    <div key="1">
      <Kicker>Slippage Desk</Kicker>
      <Big>
        A 0.24-delta spread nets <span className="text-allow">$5.19</span> a contract.
        <br />
        Crossing the spread cost <span className="text-block">$1.78 of it</span>.
      </Big>
      <Note>
        A win banks $32.43 against a $81.09 stop, so breakeven is 71.4%. A 0.24 short
        delta implies 76% finish out of the money. The entire edge is 4.6 percentage
        points, and execution took 34% of it.
      </Note>
    </div>,

    // 2: the gap in the field
    <div key="2">
      <Kicker>I read all 47 submissions</Kicker>
      <Big>
        Ten govern an LLM with deterministic gates.
        <br />
        <span className="text-block">None measure whether they got filled.</span>
      </Big>
      <Note>
        Every agent here measures whether its decisions were right. Not one
        measures whether its executions were good.
      </Note>
    </div>,

    // 3: a real refusal, live from the journal
    <div key="3">
      <Kicker>Fifteen gates run before any order</Kicker>
      <Big>This one was refused.</Big>
      <div className="mt-8 max-w-4xl space-y-1.5 font-mono text-[clamp(0.8rem,1.15vw,1.05rem)]">
        {gates.slice(0, 11).map((v, n) => (
          <div key={n} className="flex gap-4">
            <span className={v.allowed ? "text-allow" : "text-block"}>
              {v.allowed ? "PASS" : "STOP"}
            </span>
            <span className="w-56 shrink-0 text-muted">{v.gate}</span>
            <span className="text-foreground/70">{v.detail}</span>
          </div>
        ))}
      </div>
      {stopped && (
        <Note>
          Stopped on <span className="font-mono text-block">{stopped.gate}</span>.
          The refusals are the evidence the risk layer does real work.
        </Note>
      )}
    </div>,

    // 4: the model's authority
    <div key="4">
      <Kicker>The model layer</Kicker>
      <Big>
        It can shrink a trade or veto it.
        <br />
        <span className="text-muted">Nothing else.</span>
      </Big>
      <Note>
        It cannot pick a strike, change an expiry, or increase size. The clamp
        multiplies, never assigns. And when the model is unreachable this desk{" "}
        <strong className="text-foreground">refuses</strong>. Only 6 of the 47
        submissions here say what happens when their model fails at all.
      </Note>
    </div>,

    // 5: the thing nobody else has
    <div key="5">
      <Kicker>What this one measures</Kicker>
      <Big>
        {p.capture !== null ? (
          <>
            <span className="text-allow">{pct(p.capture)}</span> of theoretical
            credit captured
          </>
        ) : (
          <>Capture per bucket</>
        )}
      </Big>
      <div className="mt-8 max-w-3xl space-y-2 font-mono text-[clamp(0.85rem,1.2vw,1.1rem)]">
        {p.buckets.map((b) => (
          <div key={b.key} className="flex justify-between border-b border-edge pb-1.5">
            <span className="text-muted">{b.key}</span>
            <span className={b.capture < 0.6 ? "text-block" : "text-allow"}>
              {pct(b.capture)}
            </span>
          </div>
        ))}
      </div>
      <Note>
        Every fill scored against the mid it was priced at, per underlying,
        tenor, delta band and time of day. Buckets that fill badly get refused,
        and candidates are now ranked on the credit a bucket has actually
        delivered, not the credit it advertises.
      </Note>
    </div>,

    // 6: Alpaca
    <div key="6">
      <Kicker>Alpaca, three surfaces, separate jobs</Kicker>
      <Big>Execution never routes through MCP.</Big>
      <div className="mt-8 max-w-4xl space-y-3 text-[clamp(0.95rem,1.4vw,1.3rem)]">
        <div>
          <span className="font-mono text-allow">CLI</span> executes orders and
          verifies the book. Nine endpoints.
        </div>
        <div>
          <span className="font-mono text-allow">SDK</span> option chains with
          greeks in one call.
        </div>
        <div>
          <span className="font-mono text-allow">MCP</span> read-only research,
          launched without the trading toolset so no order tool exists to call.
        </div>
      </div>
      <Note>
        A stdio subprocess must never sit between the agent and its stops. That is
        enforced, not intended.
      </Note>
    </div>,

    // 7: the claim, and its limits
    <div key="7">
      <Kicker>What we claim</Kicker>
      <Big>
        Not that the strategy is profitable.
        <br />
        <span className="text-allow">That the agent measured itself.</span>
      </Big>
      <div className="mt-8 flex flex-wrap gap-x-14 gap-y-6 font-mono">
        {[
          ["candidates", p.considered.toLocaleString()],
          ["cleared every gate", p.approved.toLocaleString()],
          ["fills scored", String(p.fills)],
          ["given to execution", `$${p.givenUp.toFixed(2)}`],
        ].map(([k, v]) => (
          <div key={k}>
            <div className="text-xs uppercase tracking-wider text-muted">{k}</div>
            <div className="text-[clamp(1.6rem,3vw,2.6rem)] tabular-nums">{v}</div>
          </div>
        ))}
      </div>
      <Note>
        Four sessions cannot establish profitability, for anyone here. They can
        establish this. Sourced from Alpaca&apos;s own activity log, sha256{" "}
        <span className="font-mono text-sm">{p.sha}</span>, reproducible by anyone
        holding the account ID.
      </Note>
    </div>,

    // 8: close
    <div key="8">
      <Kicker>Slippage Desk</Kicker>
      <Big>
        Most agents optimise what to trade.
        <br />
        This one learns whether it can get the price.
      </Big>
      <Note>
        <span className="font-mono text-base">
          github.com/priyanshshahh/slippage-desk
          <br />
          dashboard-theta-lemon-36.vercel.app
          <br />
          paper account PA343VC6LL3T
        </span>
      </Note>
    </div>,
  ];
}
