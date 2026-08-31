"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Decision } from "@/lib/data";

const POLL_MS = 5000;
const REPLAY_STEP_MS = 1400;

type Mode = "live" | "replay";

function Line({ d }: { d: Decision }) {
  const traded = d.allowed && d.contracts > 0;
  const time = new Date(d.ts).toLocaleTimeString("en-US", { hour12: false });

  return (
    <div className="border-b border-edge/60 px-3 py-2 font-mono text-[11px] leading-relaxed">
      <div className="flex items-baseline gap-2">
        <span className="text-muted">{time}</span>
        <span className="font-semibold">
          {d.underlying} {d.kind.replace("_", " ")} {d.short_strike}/{d.long_strike}
        </span>
        <span className="text-muted">
          credit {d.credit_mid.toFixed(2)} · delta {d.short_delta.toFixed(3)}
        </span>
      </div>

      <div className="mt-1 space-y-0.5 pl-3">
        {d.verdicts.map((v, i) => (
          <div key={`${v.gate}-${i}`} className="flex gap-2">
            <span className={v.allowed ? "text-allow" : "text-block"}>
              {v.allowed ? "PASS" : "STOP"}
            </span>
            <span className="w-44 shrink-0 text-muted">{v.gate}</span>
            <span className="text-foreground/70">{v.detail}</span>
          </div>
        ))}
      </div>

      <div className="mt-1 pl-3">
        {traded ? (
          <span className="text-allow">
            → EXECUTED {d.contracts}x
            {d.fill?.capture != null &&
              ` · captured ${(d.fill.capture * 100).toFixed(0)}% of mid`}
          </span>
        ) : (
          <span className="text-block">
            → REFUSED{d.blocked_by.length ? `: ${d.blocked_by.join(", ")}` : ""}
          </span>
        )}
      </div>
    </div>
  );
}

export default function Brain() {
  // `all` is oldest-first, exactly as the journal was written.
  const [all, setAll] = useState<Decision[]>([]);
  const [mode, setMode] = useState<Mode>("live");
  const [cursor, setCursor] = useState(0);
  const [growing, setGrowing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seen = useRef(0);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/decisions", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      // The route hands back newest-first; replay needs chronological order.
      setAll([...(json.decisions as Decision[])].reverse());
      setErr(null);
      setGrowing(json.total !== seen.current && seen.current !== 0);
      seen.current = json.total;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "poll failed");
    }
  }, []);

  // Live mode polls the journal.
  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    const tick = () => {
      if (!cancelled) void load();
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [mode, load]);

  // Replay mode walks the recorded journal forward, then loops.
  //
  // Judging happens after the deadline, very likely with the market shut. A
  // live agent then renders a correct but empty screen, which reads as broken.
  // Replay streams the real decisions the agent actually made, at a watchable
  // pace, so the demo shows real work whenever someone opens it.
  useEffect(() => {
    if (mode !== "replay" || all.length === 0) return;
    const id = setInterval(() => {
      setCursor((c) => (c >= all.length ? 1 : c + 1));
    }, REPLAY_STEP_MS);
    return () => clearInterval(id);
  }, [mode, all.length]);

  function toggle() {
    if (mode === "live") {
      setCursor(1);
      setMode("replay");
    } else {
      setMode("live");
    }
  }

  const replaying = mode === "replay";
  const shown = replaying ? all.slice(0, cursor) : all;
  const feed = [...shown].reverse(); // newest at top

  return (
    <section className="rounded-lg border border-edge bg-panel">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-edge px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold">The brain</h2>
          <p className="mt-0.5 text-xs text-muted">
            Every gate the agent ran, in order, and what it decided. Refusals
            included.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2 font-mono text-[11px] text-muted">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                err
                  ? "bg-block"
                  : replaying || growing
                    ? "animate-pulse bg-allow"
                    : "bg-muted"
              }`}
            />
            {err
              ? `error: ${err}`
              : replaying
                ? `replay ${shown.length}/${all.length}`
                : `${all.length} decisions`}
          </span>

          <button
            type="button"
            onClick={toggle}
            aria-pressed={replaying}
            className="rounded border border-edge px-2.5 py-1 font-mono text-[11px] text-muted transition-colors hover:border-muted hover:text-foreground"
          >
            {replaying ? "go live" : "replay"}
          </button>
        </div>
      </header>

      {replaying && (
        <p className="border-b border-edge bg-grid px-4 py-2 text-[11px] text-muted">
          Replaying the recorded decision journal. These are real decisions the
          agent made, streamed back at a watchable pace so the demo works when
          the market is closed.
        </p>
      )}

      <div className="max-h-[30rem] overflow-y-auto">
        {feed.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-muted">
            {all.length === 0
              ? "Waiting for the agent's first decision."
              : "Starting replay…"}
          </p>
        ) : (
          feed.map((d, i) => <Line key={`${d.ts}-${d.short_symbol}-${i}`} d={d} />)
        )}
      </div>
    </section>
  );
}
