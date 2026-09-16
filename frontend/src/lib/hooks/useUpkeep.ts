// frontend/src/lib/hooks/useUpkeep.ts
//
// Whether a long, model-driven pass is running over one target — asked of the
// SERVER, not of a component (agents/frontend.md §3).
//
// This exists because the obvious alternative is wrong. A button whose spinner
// comes from its own mutation's `isPending` is telling you about a react-query
// object that dies with the component: navigate away mid-pass and come back,
// the page remounts with a fresh mutation, the button looks idle, and the next
// click starts a SECOND pass over the same files. The daemon is the only thing
// that knows what it is rewriting, so the button asks it.
//
// One query serves both kinds (`/api/v1/upkeep/runs` answers for all of them),
// and it polls on its own: a pass can also be started by the CLI or by the
// background timer, so "running" can become true without this tab doing
// anything. The idle interval is slow enough to be free on a loopback daemon
// and the running interval is fast enough that the spinner clears promptly.
import { useQuery } from "@tanstack/react-query";

import { listUpkeepRuns, type UpkeepKind, type UpkeepRunOut } from "@/lib/api/upkeep";
import { upkeepRunsKey } from "@/lib/api/queryKeys";

/** How often to re-ask while something is running, and while nothing is. */
const POLL_WHILE_RUNNING_MS = 1500;
const POLL_WHILE_IDLE_MS = 5000;

/** Every pass in flight. Polls itself; see the module comment for why. */
function useUpkeepRuns() {
  return useQuery({
    queryKey: upkeepRunsKey,
    queryFn: async () => (await listUpkeepRuns()).runs,
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? POLL_WHILE_RUNNING_MS : POLL_WHILE_IDLE_MS,
  });
}

/**
 * Is a pass running over this one partition / collection right now?
 *
 * False while the first read is still in flight, which is the honest answer to
 * give a button: the page's own optimistic pending state covers the moment
 * between a click and the first poll, and a mount that has not heard back yet
 * has no reason to claim a pass is running.
 */
export function useUpkeepRunning(kind: UpkeepKind, name: string): boolean {
  const { data } = useUpkeepRuns();
  return (data ?? []).some((run: UpkeepRunOut) => run.kind === kind && run.name === name);
}
