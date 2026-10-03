// src/lib/hooks/useServerFailures.ts — how a failed call's server has been doing: since when it fails, and how often today.
//
// The MCP-call drawer answers "is this one call, or is the server down?"
// under a failed call's error (design 6.2.07: "sentry has been failing since
// 14:20 — 7 errors in the last 24 hours"). Two reads of the invocation log the
// Activity page already reads — the server's newest calls of the last 24
// hours, and the count of its errors in that window — and no route of its own.
import { useQuery } from "@tanstack/react-query";

import { fetchCallPage } from "@/lib/api/activity";
import { mcpAllInvocationsKey } from "@/lib/api/queryKeys";
import type { Invocation } from "@/lib/activity/records";

const DAY_MS = 86_400_000;
/** The newest calls read to find where the current run of failures began. */
const RECENT = 100;

/** @ui-only What the drawer says about the server. */
export interface ServerFailures {
  /** When the run of failures that reaches the newest call began; null if it has since recovered. */
  failingSince: string | null;
  /** The server's errors in the last 24 hours. */
  errors: number;
}

/** The start of the run of non-OK calls that the newest call belongs to, if it is one. */
function failingSince(newestFirst: readonly Invocation[]): string | null {
  let since: string | null = null;
  for (const call of newestFirst) {
    if (call.status === "ok") break;
    since = call.timestamp;
  }
  return since;
}

export function useServerFailures(call: Invocation | null): ServerFailures | undefined {
  const uid = call && call.status !== "ok" ? call.resource_uid : null;
  const query = useQuery({
    queryKey: mcpAllInvocationsKey({ uid, view: "failures" }),
    enabled: uid !== null,
    queryFn: async (): Promise<ServerFailures> => {
      const since = new Date(Date.now() - DAY_MS).toISOString();
      const [recent, errors] = await Promise.all([
        fetchCallPage({ since, uid: uid ?? undefined }, RECENT),
        fetchCallPage({ since, uid: uid ?? undefined, status: "error" }, 1),
      ]);
      return { failingSince: failingSince(recent.invocations), errors: errors.total };
    },
  });
  return uid ? query.data : undefined;
}
