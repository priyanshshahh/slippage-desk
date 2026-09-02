import type { Proof } from "@/lib/data";

const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const dollars = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

/**
 * The page used to open with four numbers and assume the reader knew why they
 * mattered. A judge landing cold needs the claim before the evidence, so this
 * states the arithmetic that makes the whole project make sense.
 *
 * Those four numbers were hand-typed once and drifted: they described a $38
 * credit against a $75 stop, which matched neither config.yaml nor a single
 * real fill. Everything here now comes from proof.economics, derived in
 * scripts/proof.py from the config and the broker-verified fills.
 */
export default function Hero({ proof }: { proof: Proof | null }) {
  const capture = proof?.broker_verification?.broker_capture_ratio ?? null;
  const givenUp = proof?.totals?.given_up_to_execution_usd ?? 0;
  const e = proof?.economics ?? null;

  // Execution cost as a share of the edge it eats into. Stated as a fraction
  // rather than a rounded word, because the word was what went stale before.
  const perContractCost = e && e.contracts > 0 ? givenUp / e.contracts : null;
  const eaten =
    perContractCost !== null && e && e.expected_per_contract_usd > 0
      ? perContractCost / e.expected_per_contract_usd
      : null;

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
      {e && (
        <div className="mt-8 rounded-lg border border-edge bg-panel p-5">
          <p className="mb-4 text-sm text-muted">
            Why that matters. Every figure below is derived from the config and
            the {e.contracts} contracts actually filled:
          </p>
          <div className="flex flex-wrap items-end gap-x-8 gap-y-4 font-mono">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted">
                a win banks
              </div>
              <div className="text-2xl tabular-nums text-allow">
                +{dollars(e.win_usd)}
              </div>
            </div>
            <div className="pb-1 text-xl text-muted">vs</div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted">
                its stop costs
              </div>
              <div className="text-2xl tabular-nums text-block">
                −{dollars(e.loss_usd)}
              </div>
            </div>
            <div className="pb-1 text-xl text-muted">→</div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted">
                breakeven win rate
              </div>
              <div className="text-2xl tabular-nums">
                {pct(e.breakeven_win_rate)}
              </div>
            </div>
            <div className="pb-1 text-xl text-muted">vs</div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-muted">
                delta-implied OTM
              </div>
              <div className="text-2xl tabular-nums">
                {(e.delta_implied_otm_rate * 100).toFixed(0)}%
              </div>
            </div>
          </div>
          <p className="mt-5 max-w-3xl text-sm leading-relaxed text-foreground/80">
            The entire edge is{" "}
            <strong>{e.edge_points} percentage points</strong>, worth{" "}
            <span className="font-mono">{dollars(e.expected_per_contract_usd)}</span>{" "}
            per contract before costs.
            {perContractCost !== null && eaten !== null && (
              <>
                {" "}Crossing the bid/ask cost{" "}
                <span className="font-mono">{dollars(perContractCost)}</span> of
                that, which is <strong>{(eaten * 100).toFixed(0)}% of the edge</strong>.
              </>
            )}{" "}
            So on this horizon,{" "}
            <strong>how well you get filled matters as much as what you pick</strong>
            {capture !== null && (
              <>
                {" "}and this agent captured{" "}
                <span className="font-mono text-allow">
                  {(capture * 100).toFixed(1)}%
                </span>{" "}
                of theoretical credit, giving up{" "}
                <span className="font-mono">{money(givenUp)}</span> to execution
                across every fill.
              </>
            )}
            {capture === null && "."}
          </p>
          <p className="mt-3 max-w-3xl text-xs leading-relaxed text-muted">
            Delta-implied OTM is what a{" "}
            {(1 - e.delta_implied_otm_rate).toFixed(2)} short delta implies, not a
            measured win rate. Twenty spreads cannot establish one, and this page
            does not claim otherwise.
          </p>
        </div>
      )}
    </header>
  );
}
