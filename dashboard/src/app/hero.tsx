import type { Proof } from "@/lib/data";

const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/**
 * The page used to open with four numbers and assume the reader knew why they
 * mattered. A judge landing cold needs the claim before the evidence, so this
 * states the arithmetic that makes the whole project make sense.
 */
export default function Hero({ proof }: { proof: Proof | null }) {
  const capture = proof?.broker_verification?.broker_capture_ratio ?? null;
  const givenUp = proof?.totals?.given_up_to_execution_usd ?? 0;

  return (
    <header className="mb-10">
      <div className="mb-3 flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
        <span>Alpaca AI Trading Agents Hackathon</span>
        <span className="text-edge">·</span>
        <span>paper account PA343VC6LL3T</span>
      </div>

      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
        Slippage Desk
      </h1>
      <p className="mt-3 max-w-2xl text-lg text-foreground/90">
        The options agent that measures its own execution.
      </p>

      {/* The arithmetic. This is the whole argument in four numbers. */}
      <div className="mt-8 rounded-lg border border-edge bg-panel p-5">
        <p className="mb-4 text-sm text-muted">
          Why that matters, on a four-session horizon:
        </p>
        <div className="flex flex-wrap items-end gap-x-8 gap-y-4 font-mono">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">
              a 0.24-delta spread pays
            </div>
            <div className="text-2xl tabular-nums text-allow">+$38</div>
          </div>
          <div className="pb-1 text-xl text-muted">−</div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">
              its stop costs
            </div>
            <div className="text-2xl tabular-nums text-block">−$75</div>
          </div>
          <div className="pb-1 text-xl text-muted">→</div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">
              breakeven win rate
            </div>
            <div className="text-2xl tabular-nums">66.7%</div>
          </div>
          <div className="pb-1 text-xl text-muted">vs</div>
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">
              actual at that delta
            </div>
            <div className="text-2xl tabular-nums">~76%</div>
          </div>
        </div>
        <p className="mt-5 max-w-3xl text-sm leading-relaxed text-foreground/80">
          The entire edge is <strong>nine percentage points</strong>. Crossing the
          bid/ask on entry and exit eats a third of it. So on this horizon,
          <strong> how well you get filled matters as much as what you pick</strong>
          {capture !== null && (
            <>
              {" "}— and this agent captured{" "}
              <span className="font-mono text-allow">
                {(capture * 100).toFixed(1)}%
              </span>{" "}
              of theoretical credit, giving up{" "}
              <span className="font-mono">{money(givenUp)}</span> to execution.
            </>
          )}
          .
        </p>
      </div>
    </header>
  );
}
