const CARDS = [
  {
    k: "What the field does",
    v: "33 submissions",
    n: "Ten govern an LLM with deterministic risk gates. Every one measures whether its decisions were right.",
    tone: "muted" as const,
  },
  {
    k: "What nobody measures",
    v: "0 of 33",
    n: "Not one measures whether its executions were good. Fill quality is invisible to every other agent here.",
    tone: "block" as const,
  },
  {
    k: "What this one does",
    v: "Per-bucket capture",
    n: "Scores every fill against the mid it was priced at, learns capture per (symbol, tenor, delta, time of day), and refuses buckets where it cannot get filled.",
    tone: "allow" as const,
  },
];

const TONE = {
  muted: "text-muted",
  block: "text-block",
  allow: "text-allow",
};

/** The differentiator, stated before the reader has to infer it from data. */
export default function Claim() {
  return (
    <section className="mb-10">
      <h2 className="mb-1 text-sm font-semibold">Why this is different</h2>
      <p className="mb-4 text-xs text-muted">
        Read before the numbers below, or they look like everyone else&apos;s.
      </p>
      <div className="grid gap-3 md:grid-cols-3">
        {CARDS.map((c) => (
          <div key={c.k} className="rounded-lg border border-edge bg-panel p-4">
            <div className="text-[11px] uppercase tracking-wider text-muted">
              {c.k}
            </div>
            <div className={`mt-1.5 font-mono text-xl ${TONE[c.tone]}`}>{c.v}</div>
            <p className="mt-2 text-xs leading-relaxed text-foreground/75">{c.n}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 rounded-lg border border-edge bg-grid px-4 py-3 text-xs leading-relaxed text-foreground/75">
        <strong className="text-foreground">The honest part.</strong> Four
        sessions cannot establish that a strategy is profitable, for anyone in
        this hackathon. What four sessions <em>can</em> establish is that an
        agent measured its own execution and acted on it — and every number on
        this page is reconcilable against the paper account ID above, sourced
        from Alpaca&apos;s own activity log rather than our bookkeeping.
      </div>
    </section>
  );
}
