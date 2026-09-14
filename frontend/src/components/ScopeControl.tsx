// frontend/src/components/ScopeControl.tsx
//
// ScopeControl: ONE resource's answer to "who does this reach?" — it owns both
// the resource's `enabled` flag and its per-agent activation scope
// (ADR per-agent-resource-scope). It replaces the old pair of controls (an
// enable Switch in the page header + a separate "Activation scope" card further
// down), which expressed the same "reaches nobody" state twice: `enabled=false`
// in one place and `scope=[]` (the dormant warning) in another.
//
// The BUTTONS, LABELS and AGENT PANEL are not here: they live in
// `components/reach/ReachControl.tsx`, shared with the bulk bar
// (`BulkReachActions`) so the row control, the detail-page control and the
// selection-wide control cannot drift into three different three-way choices.
// This file is the single-resource DATA half: which segment is live, and what
// each one writes.
//
// Data: GET/PUT /resources/{kind}/{name}/scope (useResourceScope /
// useUpdateResourceScope) plus POST .../enable|disable
// (useEnableResource/useDisableResource).
//
// The scope value is a single axis: a list of agent names.
//   null  → active for every agent ("Every agent")
//   []    → active for no agent (dormant)
//   [...] → active only for the named agents
// Layered on top of it, the resource's own `enabled` flag is the control's
// first state: disabled beats any scope. Disabling deliberately LEAVES the
// scope untouched, so re-enabling restores the agent selection the user had.
//
// Mutation pattern: the two whole-value segments write immediately, because
// each already names a complete state. The agent list does not — a selection is
// only finished when the user stops picking — so ReachControl stages it and
// hands it over once, on close:
//   - "Disabled" posts .../disable and writes no scope.
//   - "Every agent" enables if needed and writes `null`.
//   - "Selected agents" opens the list and writes NOTHING yet.
//   - Closing the list enables if needed and writes the staged list, once, if
//     it differs from what is stored.
//
// Kinds that declare no scope still need enable/disable — this control owns it
// — so they fall back to the shared two-segment Disabled/Enabled group.
//
// The control also sits in the status column of every resource LIST, one
// instance per row. Mounting the per-resource scope query once per row would
// turn one list render into one GET per row, so the list callers pass `scope`
// straight from the payload they already fetched (`ResourceOut.scope` /
// `SkillOut.scope`, or a merge of `GET /resources?kind=…` where the kind has a
// dedicated list endpoint) and the query stays off: the list costs zero extra
// requests. The detail pages pass nothing and keep fetching, since they render
// one resource.
import { ReachControl, type ReachMode } from "@/components/reach/ReachControl";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import {
  useResourceScope,
  useUpdateResourceScope,
  type ResourceScope,
  type Scope,
} from "@/lib/hooks/useScope";

interface Props {
  kind: string;
  name: string;
  enabled: boolean;
  /** Pre-fetched scope from a list payload (`null` = every agent). Omit it to
   *  let the control fetch its own; `undefined` is "not supplied", never a
   *  value. */
  scope?: Scope | null;
}

export function ScopeControl({ kind, name, enabled, scope: presetScope }: Props) {
  const prefetched = presetScope !== undefined;
  const { data: fetchedScope } = useResourceScope(kind, name, !prefetched);
  const scopeData: ResourceScope | undefined = prefetched
    ? { scope: presetScope, supports_scope: true }
    : fetchedScope;
  const update = useUpdateResourceScope(kind, name);
  const enable = useEnableResource();
  const disable = useDisableResource();

  const busy = update.isPending || enable.isPending || disable.isPending;
  // While the scope query is in flight, assume the kind supports scope; the
  // fallback only matters once the server has said otherwise.
  const supportsScope = scopeData ? scopeData.supports_scope : true;
  const scope = scopeData?.scope ?? null;

  const mode: ReachMode = !enabled ? "disabled" : scope === null ? "every" : "selected";

  const enableIfNeeded = () => {
    if (!enabled) enable.mutate({ kind, name });
  };

  const commitAgents = (staged: string[]) => {
    // Enabling is part of what the segment means on a disabled resource, but it
    // waits for the close like the scope does: writing on open is what moved
    // the row out from under the panel.
    enableIfNeeded();
    const current = scope;
    const unchanged =
      current !== null &&
      current.length === staged.length &&
      current.every((agent) => staged.includes(agent));
    if (unchanged) return;
    update.mutate(staged);
  };

  return (
    <ReachControl
      mode={mode}
      supportsScope={supportsScope}
      busy={busy}
      initialAgents={scope ?? []}
      onDisabled={() => disable.mutate({ kind, name })}
      onEveryAgent={() => {
        enableIfNeeded();
        if (scope !== null) update.mutate(null);
      }}
      onSelectedAgents={commitAgents}
    />
  );
}
