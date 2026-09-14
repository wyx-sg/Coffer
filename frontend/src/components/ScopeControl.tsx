// frontend/src/components/ScopeControl.tsx
//
// ScopeControl: ONE resource's answer to "where does this reach?" — it owns
// both the resource's `enabled` flag and its activation scope (ADR
// per-agent-resource-scope). It replaces the old pair of controls (an enable
// Switch in the page header + a separate "Activation scope" card further down),
// which expressed the same "reaches nobody" state twice: `enabled=false` in one
// place and a dormant scope in another.
//
// The BUTTON, the LABELS and the panel are not here: they live in
// `components/reach/ReachControl.tsx`, shared with the bulk bar
// (`BulkReachActions`) so the row control, the detail-page control and the
// selection-wide control cannot drift into three different answers to the same
// question. This file is the single-resource DATA half: which state is live,
// what each choice writes, and — because only a single resource has an answer —
// whether this resource reaches nobody *here*.
//
// Owning BOTH halves is the point, and it is what makes this control the whole
// of a resource's reach — one button whose label is the answer: `enabled` says
// whether it is live at all, `scope` says which agents it is live for, and
// neither alone is the answer. Reach in that sense is MACHINE-LOCAL — held in
// this vault, never converged with a remote —
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
// Mutation pattern: ReachControl stages the user's choice and hands it over
// exactly once, when its panel closes — nothing is written while the panel is
// open, whichever choice was made:
//   - "Disabled" posts .../disable and writes no scope.
//   - "Every agent" enables if needed and writes `null`.
//   - "Only selected agents" writes the staged agent list, once, if it differs
//     from what is stored, and enables if needed. It is always a list:
//     relaxing back to every agent is the "Every agent" choice above, so the
//     same state can never arrive here under a second name.
//   - A panel the user only glanced at writes nothing at all.
//
// Kinds that declare no scope still need enable/disable — this control owns it
// — so they fall back to the same button over a two-choice Disabled/Enabled
// panel.
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
    // Enabling is part of what the choice means on a disabled resource, but it
    // waits for the close like the scope does: writing while the panel was open
    // is what moved the row out from under it.
    enableIfNeeded();
    if (sameScope(scope, staged)) return;
    // Always a list. "Every agent" is its own choice writing `null` through
    // `onEverywhere`, so a relaxed-to-everything selection cannot arrive here
    // as `{agents: null}` — the same state under a second name.
    update.mutate(staged);
  };

  // "Inactive here" is judged against the agents registered in THIS vault —
  // the only ones a scope set on this machine could ever name.
  //
  // It earns its keep MORE now that reach is one button, not less. The button
  // reports the scope, and a scope naming only agents this machine has never
  // heard of reads as a perfectly healthy "1 agent" while reaching nobody; the
  // note is the only thing that says otherwise without opening the panel, and
  // it is what turns the button amber.
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
