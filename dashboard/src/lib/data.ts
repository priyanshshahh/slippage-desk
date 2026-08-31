import { readFile } from "node:fs/promises";
import path from "node:path";

// Written by scripts/snapshot-data.mjs at build time. A static import is
// always bundled; a runtime file read in a serverless function is not.
import snapshot from "./snapshot.json";

// The dashboard is a read-only view of what the agent already wrote. It
// reaches into the repo's data directory rather than duplicating any of
// the engine's logic, so it can never disagree with the agent about what
// happened.
// Bundled snapshot first (what a deploy has), then the live sibling
// directory the agent writes to on a developer machine.
const DATA_DIRS = [
  path.join(process.cwd(), "data"),
  path.join(process.cwd(), "..", "data"),
];

async function readFrom(file: string): Promise<string> {
  let lastErr: unknown;
  for (const dir of DATA_DIRS) {
    try {
      return await readFile(path.join(dir, file), "utf8");
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr;
}

export type Verdict = { gate: string; allowed: boolean; detail: string };

export type Fill = {
  order_id: string | null;
  status: string | null;
  submitted_limit: number | null;
  filled_price: number | null;
  bucket?: string;
  capture?: number;
};

export type Decision = {
  ts: string;
  underlying: string;
  kind: string;
  expiry: string;
  short_strike: number;
  long_strike: number;
  short_symbol: string;
  long_symbol: string;
  credit_mid: number;
  credit_crossable: number;
  max_loss_per_contract: number;
  short_delta: number;
  contracts: number;
  allowed: boolean;
  blocked_by: string[];
  verdicts: Verdict[];
  state: Record<string, number | string>;
  fill: Fill | null;
};

export type OpenSpread = {
  underlying: string;
  kind: string;
  expiry: string;
  short_symbol: string;
  long_symbol: string;
  contracts: number;
  entry_credit: number;
  max_loss_per_contract: number;
  bucket: string;
  opened_at: string;
};

export type Bucket = {
  key: string;
  submitted: number;
  filled: number;
  captures: number[];
};

async function readJson<T>(file: string, fallback: T): Promise<T> {
  try {
    return JSON.parse(await readFrom(file)) as T;
  } catch {
    // A missing file means the agent has not produced that artefact yet,
    // which is a normal empty state, not an error worth surfacing.
    return fallback;
  }
}

export async function getDecisions(): Promise<Decision[]> {
  // Live file first so a developer sees the agent's journal grow in real
  // time; the bundled snapshot is what a deploy actually serves.
  try {
    const raw = await readFrom("decisions.jsonl");
    const live = raw
      .split("\n")
      .filter((l) => l.trim())
      .map((l) => JSON.parse(l) as Decision);
    if (live.length) return live;
  } catch {
    /* fall through to the snapshot */
  }
  return snapshot.decisions as unknown as Decision[];
}

export async function getOpenSpreads(): Promise<OpenSpread[]> {
  const live = await readJson<OpenSpread[]>("open_spreads.json", []);
  return live.length ? live : (snapshot.openSpreads as unknown as OpenSpread[]);
}

export async function getBuckets(): Promise<Bucket[]> {
  let raw = await readJson<Record<string, Omit<Bucket, "key">>>(
    "execution_quality.json",
    {},
  );
  if (!Object.keys(raw).length) {
    raw = snapshot.buckets as unknown as Record<string, Omit<Bucket, "key">>;
  }
  return Object.entries(raw).map(([key, v]) => ({ key, ...v }));
}

/** Shrunk toward 1.0 so a bucket with one lucky fill does not look expert. */
export function shrunkCapture(b: Bucket, prior = 3): number {
  const n = b.captures.length;
  if (n === 0) return 1.0;
  const mean = b.captures.reduce((a, c) => a + c, 0) / n;
  return (n * mean + prior * 1.0) / (n + prior);
}

export function rejectionsByGate(decisions: Decision[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const d of decisions) {
    for (const g of d.blocked_by) counts.set(g, (counts.get(g) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]);
}

/** What the agent theoretically should have collected, versus what reached
 *  the account. The gap is the cost of execution, which on this horizon is
 *  the same order of magnitude as the entire strategy edge. */
export function executionEconomics(decisions: Decision[]) {
  let theoretical = 0;
  let captured = 0;
  let fills = 0;
  for (const d of decisions) {
    const price = d.fill?.filled_price;
    if (price == null) continue;
    fills++;
    theoretical += d.credit_mid * 100 * d.contracts;
    captured += Math.abs(price) * 100 * d.contracts;
  }
  return {
    fills,
    theoretical,
    captured,
    givenUp: theoretical - captured,
    ratio: theoretical > 0 ? captured / theoretical : null,
  };
}
