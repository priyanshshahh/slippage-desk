import Brain from "./brain";
import Claim from "./claim";
import Hero from "./hero";
import SurfacePanel from "./surfaces";
import {
  getBuckets,
  getDecisions,
  getOpenSpreads,
  getProof,
  getSurfaces,
  executionEconomics,
  rejectionsByGate,
  shrunkCapture,
  type Decision,
} from "@/lib/data";

// The journal is written by a separate process, so never cache it.
export const dynamic = "force-dynamic";

const strike = (n: number) =>
  Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, "");

const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-edge bg-panel px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 font-mono text-2xl tabular-nums">{value}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-edge bg-panel">
      <header className="border-b border-edge px-4 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function GateChart({ rows }: { rows: [string, number][] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted">No rejections recorded yet.</p>;
  }
  const max = Math.max(...rows.map(([, n]) => n));
  return (
    <ul className="space-y-2">
      {rows.map(([gate, n]) => (
        <li key={gate} className="grid grid-cols-[11rem_1fr_2.5rem] items-center gap-3">
          <span className="truncate font-mono text-xs text-muted" title={gate}>
            {gate}
          </span>
          <span className="h-5 rounded bg-grid" role="presentation">
            <span
              className="block h-5 rounded bg-block/70"
              style={{ width: `${Math.max(2, (n / max) * 100)}%` }}
            />
          </span>
          <span className="text-right font-mono text-xs tabular-nums">{n}</span>
        </li>
      ))}
    </ul>
  );
}

function DecisionRow({ d }: { d: Decision }) {
  const when = new Date(d.ts).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  const traded = d.allowed && d.contracts > 0;
  return (
    <tr className="border-t border-edge align-top">
      <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs text-muted">{when}</td>
      <td className="py-2 pr-3">
        <div className="font-mono text-xs">
          {d.underlying} {strike(d.short_strike)}/{strike(d.long_strike)}
        </div>
        <div className="text-[11px] text-muted">{d.kind.replace("_", " ")}</div>
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs tabular-nums">
        {d.credit_mid.toFixed(2)}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs tabular-nums text-muted">
        {d.short_delta.toFixed(3)}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs tabular-nums text-muted">
        {money(d.max_loss_per_contract)}
      </td>
      <td className="py-2 pr-3">
        {traded ? (
          <span className="font-mono text-xs text-allow">
            traded {d.contracts}x
            {d.fill?.capture != null && (
              <span className="ml-1 text-muted">
                @ {(d.fill.capture * 100).toFixed(0)}% capture
              </span>
            )}
          </span>
        ) : (
          <span className="font-mono text-xs text-block">
            {d.blocked_by.join(", ") || "not sized"}
          </span>
        )}
      </td>
    </tr>
  );
}

export default async function Page() {
  const [decisions, open, buckets, surfaces, proof] = await Promise.all([
    getDecisions(),
    getOpenSpreads(),
    getBuckets(),
    getSurfaces(),
    getProof(),
  ]);

  // Every candidate is journaled; only the best per poll is submitted. A
  // decision with a fill record is a trade, an approved one merely cleared
  // the gates.
  const approved = decisions.filter((d) => d.allowed && d.contracts > 0);
  const traded = decisions.filter((d) => d.fill != null);
  const gates = rejectionsByGate(decisions);
  const openRisk = open.reduce(
    (a, s) => a + s.contracts * s.max_loss_per_contract,
    0,
  );
  const recent = [...decisions].reverse().slice(0, 25);
  const scored = buckets.filter((b) => b.captures.length > 0);
  const econ = executionEconomics(decisions, proof);

  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">
      <Hero proof={proof} />
      <Claim />

      {decisions.length === 0 ? (
        <div className="rounded-lg border border-edge bg-panel px-4 py-8 text-center">
          <p className="text-sm">No decisions recorded yet.</p>
          <p className="mt-1 text-xs text-muted">
            Run the agent, or seed a demo journal with{" "}
            <code className="font-mono">python -m scripts.seed_demo_data</code>.
          </p>
        </div>
      ) : (
        <>
          <h2 className="mb-1 text-sm font-semibold">Live evidence</h2>
          <p className="mb-4 text-xs text-muted">
            From the agent running on the paper account right now. Reload to
            refresh.
          </p>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Considered" value={String(decisions.length)} note="candidates evaluated" />
            <Stat
              label="Traded"
              value={String(traded.length)}
              note={`${approved.length} cleared every gate`}
            />
            <Stat
              label="Credit captured"
              value={econ.ratio == null ? "-" : `${(econ.ratio * 100).toFixed(0)}%`}
              note={`across ${econ.fills} fill${econ.fills === 1 ? "" : "s"}${econ.brokerVerified ? ", broker-verified" : ""}`}
            />
            <Stat
              label="Lost to execution"
              value={money(econ.givenUp)}
              note={`${money(openRisk)} open risk · ${gates.length} gates fired`}
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Panel
              title="Why the agent declined"
              subtitle="Rejections by gate. A candidate can trip more than one."
            >
              <GateChart rows={gates} />
            </Panel>

            <Panel
              title="Execution quality"
              subtitle="What fraction of the theoretical credit each bucket actually captures."
            >
              {scored.length === 0 ? (
                <p className="text-sm text-muted">No scored fills yet.</p>
              ) : (
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-muted">
                      <th className="pb-2 font-medium">Bucket</th>
                      <th className="pb-2 text-right font-medium">Fills</th>
                      <th className="pb-2 text-right font-medium">Capture</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scored
                      .sort((a, b) => shrunkCapture(a) - shrunkCapture(b))
                      .slice(0, 8)
                      .map((b) => {
                        const c = shrunkCapture(b);
                        return (
                          <tr key={b.key} className="border-t border-edge">
                            <td className="py-2 font-mono text-xs">{b.key}</td>
                            <td className="py-2 text-right font-mono text-xs tabular-nums text-muted">
                              {b.filled}/{b.submitted}
                            </td>
                            <td
                              className={`py-2 text-right font-mono text-xs tabular-nums ${
                                c < 0.6 ? "text-block" : "text-allow"
                              }`}
                            >
                              {(c * 100).toFixed(0)}%
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              )}
            </Panel>
          </div>

          <div className="mt-5">
            <Brain />
          </div>

          <div className="mt-5">
            <SurfacePanel data={surfaces} />
          </div>

          <div className="mt-5">
            <Panel
              title="Decision journal"
              subtitle={`Most recent ${recent.length} of ${decisions.length}.`}
            >
              <div className="overflow-x-auto">
                <table className="w-full min-w-[46rem] text-left">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-wider text-muted">
                      <th className="pb-2 pr-3 font-medium">When</th>
                      <th className="pb-2 pr-3 font-medium">Spread</th>
                      <th className="pb-2 pr-3 text-right font-medium">Credit</th>
                      <th className="pb-2 pr-3 text-right font-medium">Delta</th>
                      <th className="pb-2 pr-3 text-right font-medium">Max loss</th>
                      <th className="pb-2 font-medium">Outcome</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((d, i) => (
                      <DecisionRow key={`${d.ts}-${d.short_symbol}-${i}`} d={d} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          </div>
        </>
      )}
    </main>
  );
}
