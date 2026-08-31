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
  surfaces: await readJson("surfaces.json", null),
  proof: await readJson("proof.json", null),
};

// This also runs as `prebuild` on the deploy host, where ../data does not
// exist. Writing an empty snapshot there would clobber the committed one and
// ship a dashboard showing nothing, which is exactly what happened once.
// Only overwrite when there is actually something to write.
if (snapshot.decisions.length === 0) {
  try {
    const existing = JSON.parse(await readFile(out, "utf8"));
    if (existing?.decisions?.length) {
      console.log(
        `snapshot: no source data here, keeping the committed snapshot ` +
          `(${existing.decisions.length} decisions)`,
      );
      process.exit(0);
    }
  } catch {
    /* nothing committed either; fall through and write the empty one */
  }
}

await mkdir(path.dirname(out), { recursive: true });
await writeFile(out, JSON.stringify(snapshot));
console.log(
  `snapshot: ${snapshot.decisions.length} decisions, ` +
    `${Object.keys(snapshot.buckets).length} buckets, ` +
    `${snapshot.surfaces?.surfaces?.length ?? 0} surfaces -> src/lib/snapshot.json`,
);
