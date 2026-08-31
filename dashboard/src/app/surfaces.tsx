import type { Surfaces } from "@/lib/data";

const LAYER_NOTE: Record<string, string> = {
  CLI: "The agent's hands. Execution and book verification.",
  SDK: "The agent's eyes. Chains with greeks in one call.",
  MCP: "A second opinion. Read-only by construction.",
};

export default function SurfacePanel({ data }: { data: Surfaces | null }) {
  if (!data) return null;

  const layers = [...new Set(data.surfaces.map((s) => s.layer))];

  return (
    <section className="rounded-lg border border-edge bg-panel">
      <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-edge px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">Alpaca surfaces</h2>
          <p className="mt-0.5 max-w-3xl text-xs text-muted">
            {data.architecture}
          </p>
        </div>
        <span className="font-mono text-[11px] text-muted">
          <span className={data.passing === data.total ? "text-allow" : "text-block"}>
            {data.passing}/{data.total}
          </span>{" "}
          responding
        </span>
      </header>

      <div className="p-4">
        {layers.map((layer) => (
          <div key={layer} className="mb-4 last:mb-0">
            <div className="mb-1.5 flex items-baseline gap-2">
              <span className="rounded bg-grid px-1.5 py-0.5 font-mono text-[10px] font-semibold">
                {layer}
              </span>
              <span className="text-[11px] text-muted">{LAYER_NOTE[layer]}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[42rem] text-left">
                <tbody>
                  {data.surfaces
                    .filter((s) => s.layer === layer)
                    .map((s) => (
                      <tr key={s.surface} className="border-t border-edge/60">
                        <td className="w-6 py-1.5 font-mono text-[11px]">
                          <span className={s.ok ? "text-allow" : "text-block"}>
                            {s.ok ? "ok" : "!!"}
                          </span>
                        </td>
                        <td className="w-56 py-1.5 pr-3 font-mono text-[11px]">
                          {s.surface}
                        </td>
                        <td className="py-1.5 pr-3 text-[11px] text-muted">{s.job}</td>
                        <td className="w-40 py-1.5 pr-3 font-mono text-[11px] text-foreground/70">
                          {s.detail}
                        </td>
                        <td className="w-14 py-1.5 text-right font-mono text-[11px] tabular-nums text-muted">
                          {s.ms}ms
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
