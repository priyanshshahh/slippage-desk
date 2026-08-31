import { getDecisions } from "@/lib/data";

// The journal is appended by a separate process on a 60s loop, so this must
// never be cached: a stale brain feed is worse than no brain feed.
export const dynamic = "force-dynamic";

export async function GET() {
  const all = await getDecisions();
  // Newest first, capped. The full journal is the audit record; this is a feed.
  return Response.json({ decisions: all.slice(-60).reverse(), total: all.length });
}
