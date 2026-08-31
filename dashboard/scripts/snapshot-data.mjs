// Bundle a snapshot of the agent's journal for deployment.
//
// The dashboard reads ../data on a developer machine, where the agent is
// actively writing. A serverless deploy has neither that directory nor the
// agent, and reading files at request time is unreliable there: Next only
// bundles what it can trace statically, and a runtime-built path is not
// traceable. So the build also emits a real JSON module, which is a static
// import and therefore always bundled.
//
// The deployed page is a snapshot as of deploy time, which is exactly what
// Replay Mode is for: judges see the real decisions the agent made,
// streamed back, at any hour.
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const from = path.join(process.cwd(), "..", "data");
const out = path.join(process.cwd(), "src", "lib", "snapshot.json");

async function readJson(file, fallback) {
  try {
    return JSON.parse(await readFile(path.join(from, file), "utf8"));
  } catch {
    return fallback;
  }
}

async function readJsonl(file) {
  try {
    const raw = await readFile(path.join(from, file), "utf8");
    return raw.split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
  } catch {
    return [];
  }
}

const snapshot = {
  generatedAt: new Date().toISOString(),
  decisions: await readJsonl("decisions.jsonl"),
  buckets: await readJson("execution_quality.json", {}),
  openSpreads: await readJson("open_spreads.json", []),
};

await mkdir(path.dirname(out), { recursive: true });
await writeFile(out, JSON.stringify(snapshot));
console.log(
  `snapshot: ${snapshot.decisions.length} decisions, ` +
    `${Object.keys(snapshot.buckets).length} buckets -> src/lib/snapshot.json`,
);
