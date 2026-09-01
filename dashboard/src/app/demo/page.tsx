import { getBuckets, getDecisions, getProof, shrunkCapture } from "@/lib/data";
import DemoDeck from "./deck";

export const dynamic = "force-dynamic";

/**
 * A full-screen, keyboard-advanced walkthrough for recording the submission
 * video. The written script existed but still required deciding what to show
 * and when; this removes that. Open, press space, narrate.
 *
 * Every number is live, so the recording cannot drift from the account.
 */
export default async function DemoPage() {
  const [decisions, buckets, proof] = await Promise.all([
    getDecisions(),
    getBuckets(),
    getProof(),
  ]);

  const refusal = [...decisions]
    .reverse()
    .find((d) => d.blocked_by.length > 0 && d.verdicts.length > 8);
  const executed = [...decisions].reverse().find((d) => d.fill != null);
  const scored = buckets
    .filter((b) => b.captures.length > 0)
    .map((b) => ({ key: b.key, capture: shrunkCapture(b) }))
    .sort((a, b) => a.capture - b.capture)
    .slice(0, 5);

  return (
    <DemoDeck
      considered={decisions.length}
      approved={decisions.filter((d) => d.allowed && d.contracts > 0).length}
      capture={proof?.broker_verification?.broker_capture_ratio ?? null}
      givenUp={proof?.totals?.given_up_to_execution_usd ?? 0}
      fills={proof?.broker_verification?.paired_spreads ?? 0}
      sha={proof?.sha256?.slice(0, 16) ?? ""}
      refusal={refusal ?? null}
      executed={executed ?? null}
      buckets={scored}
    />
  );
}
