// frontend/src/components/ScopeControl.tsx
//
// ScopeControl: ONE resource's answer to "where does this reach?" — it owns
// both the resource's `enabled` flag and its activation scope (ADR
// per-agent-resource-scope). It replaces the old pair of controls (an enable
// Switch in the page header + a separate "Activation scope" card further down),
// which expressed the same "reaches nobody" state twice: `enabled=false` in one
// place and a dormant scope in another.
//
// The BUTTONS, LABELS and the restriction panel are not here: they live in
// `components/reach/ReachControl.tsx`, shared with the bulk bar
// (`BulkReachActions`) so the row control, the detail-page control and the
// selection-wide control cannot drift into three different three-way choices.
// This file is the single-resource DATA half: which segment is live, what each
// one writes, and — because only a single resource has an answer — whether this
// resource reaches nobody *here*.
//
// Owning BOTH halves is the point, and it is what makes this control the whole
// of a resource's reach: `enabled` says whether it is live at all, `scope` says
// which agents it is live for, and neither alone is the answer. Reach in that
// sense is MACHINE-LOCAL — held in this vault, never converged with a remote —
// so every machine the user works on sets its own, and this control is where
// that is set. ReachControl's panel tells the user so; this file is why there
// is one place to tell them.
//
// Data: GET/PUT /resources/{kind}/{name}/scope (useResourceScope /
// useUpdateResourceScope) plus POST .../enable|disable
// (useEnableResource/useDisableResource). `useAgents()` supplies the vocabulary
// the "inactive here" verdict is judged against — the agents registered on this
// machine, which is the only "here" there is.
//
// The scope value names agents:
//   null              → active for every agent
//   {agents: [...]}   → only those agents
//   {agents: []}      → dormant (it matches nobody)
// Layered on top of it, the resource's own `enabled` flag is the control's
// first state: disabled beats any scope. Disabling deliberately LEAVES the
// scope untouched, so re-enabling restores the selection the user had.
//
// Mutation pattern: the two whole-value segments write immediately, because
// each already names a complete state. The pick-list does not — a selection is
// only finished when the user stops picking — so ReachControl stages it and
// hands the whole scope over once, on close:
//   - "Disabled" posts .../disable and writes no scope.
//   - "Everywhere" enables if needed and writes `null`.
//   - "Restricted…" opens the pick-list and writes NOTHING yet.
//   - Closing it enables if needed and writes the staged scope, once, if it
//     differs from what is stored — normalised back to `null` when the user has
//     relaxed it to every agent.
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
import { useTranslation } from "react-i18next";

import { ReachControl, type ReachMode } from "@/components/reach/ReachControl";
import { useAgents } from "@/lib/hooks/useAgents";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import {
  useResourceScope,
  useUpdateResourceScope,
  UNRESTRICTED,
  type ResourceScope,
  type Scope,
} from "@/lib/hooks/useScope";
import { isDormantHere, sameScope } from "@/lib/scope";

interface Props {
  kind: string;
  name: string;
  enabled: boolean;
  /** Pre-fetched scope from a list payload (`null` = everywhere). Omit it to
   *  let the control fetch its own; `undefined` is "not supplied", never a
   *  value. */
  scope?: Scope | null;
}

export function ScopeControl({ kind, name, enabled, scope: presetScope }: Props) {
  const { t } = useTranslation();
  const prefetched = presetScope !== undefined;
  const { data: fetchedScope } = useResourceScope(kind, name, !prefetched);
  const scopeData: ResourceScope | undefined = prefetched
    ? { scope: presetScope, supports_scope: true }
    : fetchedScope;
  const { data: agentsData } = useAgents();
  const update = useUpdateResourceScope(kind, name);
  const enable = useEnableResource();
  const disable = useDisableResource();

  const busy = update.isPending || enable.isPending || disable.isPending;
  // While the scope query is in flight, assume the kind supports scope; the
  // fallback only matters once the server has said otherwise.
  const supportsScope = scopeData ? scopeData.supports_scope : true;
  const scope = scopeData?.scope ?? null;

  const mode: ReachMode = !enabled ? "disabled" : scope === null ? "everywhere" : "restricted";

  const enableIfNeeded = () => {
    if (!enabled) enable.mutate({ kind, name });
  };

  const commitScope = (staged: Scope) => {
    // Enabling is part of what the segment means on a disabled resource, but it
    // waits for the close like the scope does: writing on open is what moved
    // the row out from under the panel.
    enableIfNeeded();
    if (sameScope(scope, staged)) return;
    // "Every agent" is "everywhere", which the wire spells `null` — storing
    // `{agents: null}` instead would be the same state under a second name.
    update.mutate(sameScope(staged, UNRESTRICTED) ? null : staged);
  };

  // "Inactive here" is judged against the agents registered in THIS vault —
  // the only ones a scope set on this machine could ever name.
  const note = isDormantHere(
    scope,
    (agentsData ?? []).map((a) => a.name),
  )
    ? t("scope.inactiveHereAgent")
    : undefined;

  return (
    <ReachControl
      mode={mode}
      supportsScope={supportsScope}
      busy={busy}
      initialScope={scope}
      note={note}
      onDisabled={() => disable.mutate({ kind, name })}
      onEverywhere={() => {
        enableIfNeeded();
        if (scope !== null) update.mutate(null);
      }}
      onRestricted={commitScope}
    />
  );
}
