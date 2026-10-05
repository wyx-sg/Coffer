// frontend/src/components/ScopeControl.tsx
//
// ScopeControl: ONE resource's answer to "where does this reach?" — it owns
// both the resource's `enabled` flag and its activation scope (ADR
// per-agent-resource-scope), as the single button + popover of
// `components/reach/ReachControl.tsx`. That file is the shared UI; this one is
// the single-resource DATA half: which mode is live, what each choice writes
// (`lib/reach/useReachWrites.ts`), and whether this resource reaches nobody
// *here*.
//
// Data: GET/PUT /resources/{uid}/scope plus POST .../enable|disable. The
// control also sits in the reach column of every resource LIST, one instance
// per row, so list callers pass `scope` straight from the payload they already
// fetched and the query stays off; a detail page passes nothing and fetches.
//
// The scope value names agents by UID: `null` = every agent, `{agents: [...]}`
// = only those (never an empty list). The resource's own `enabled` flag is
// the first mode: Off beats any scope, and turning a resource off leaves the
// scope untouched, so turning it back on restores the selection.
//
// Every choice saves at once and the popover says how it went; a write that
// fails stays in the popover on the agent's row (Retry / Untick), never a toast.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import { reachModeOf } from "@/lib/reach/reachState";
import { useReachWrites } from "@/lib/reach/useReachWrites";
import { useAgents } from "@/lib/hooks/useAgents";
import { useResourceScope, type Scope } from "@/lib/hooks/useScope";
import { isDormantHere } from "@/lib/scope";

interface Props {
  /** Which kind this resource is. Not part of any request — the routes take the
   *  uid alone — but it decides which of the per-kind list keys a write
   *  refreshes. */
  kind: string;
  /** The resource this control is about. */
  uid: string;
  enabled: boolean;
  /** Pre-fetched scope from a list payload (`null` = everywhere). Omit it to
   *  let the control fetch its own; `undefined` is "not supplied", never a
   *  value. */
  scope?: Scope | null;
  /** The resource's name, shown in the popover head. */
  resourceName?: string;
}

export function ScopeControl({ kind, uid, enabled, scope: presetScope, resourceName }: Props) {
  const { t } = useTranslation();
  const prefetched = presetScope !== undefined;
  const { data: fetchedScope } = useResourceScope(uid, !prefetched);
  const { data: agentsData } = useAgents();
  const stored = (prefetched ? presetScope : fetchedScope?.scope) ?? null;
  const writes = useReachWrites(kind, uid, enabled, stored);

  // The value just written wins until the refetch brings the same news.
  const shown = writes.value ?? { enabled, scope: stored };
  const mode = reachModeOf(shown);

  // "Inactive here" is judged against the agents registered in THIS vault, and
  // not on an Off resource: there the button already says "Off", which is the
  // whole reason it reaches nobody.
  const note =
    mode !== "disabled" &&
    isDormantHere(
      shown.scope,
      (agentsData ?? []).map((a) => a.uid),
    )
      ? t("scope.inactiveHereAgent")
      : undefined;

  return (
    <ReachControl
      mode={mode}
      initialScope={shown.scope}
      note={note}
      resourceName={resourceName}
      saveState={writes.state}
      failure={writes.failure}
      onClose={writes.flush}
      onDisabled={writes.disable}
      onEverywhere={writes.everywhere}
      onRestricted={writes.restricted}
    />
  );
}
