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
// Data: GET/PUT /resources/{uid}/scope (useResourceScope /
// useUpdateResourceScope) plus POST .../enable|disable
// (useEnableResource/useDisableResource). `useAgents()` supplies the vocabulary
// the "inactive here" verdict is judged against — the agents registered on this
// machine, which is the only "here" there is.
//
// The scope value names agents by UID:
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
//
// Which is why `supportsScope` is a PROP and not only a server answer. Whether
// a kind declares a scope at all arrives on the very query a list row
// deliberately does not run, so a prefetching row cannot learn it — it used to
// simply assert `supports_scope: true`, which made every row of a kind with no
// scope claim a per-agent reach the server would refuse to write. A row's
// caller knows its kind at the call site, so it says so; a detail page omits
// it and the fetched answer governs. `knowledge` and `memory` are the kinds
// that pass `false`: every enabled collection and partition is served to every
// agent, and only `enabled` decides anything.
//
// Passing `false` also means there is no scope to report, so a value left in
// the row payload from when the kind was scoped is normalised away here rather
// than in each caller — otherwise the button would read "Enabled" over a panel
// with neither of its two choices checked.
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import { reachModeOf, type ReachMode } from "@/components/reach/reachState";
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
  /** Which kind this resource is. Not part of any request — the routes take the
   *  uid alone — but it decides which of the per-kind list keys a write
   *  refreshes, and whether the kind declares a scope at all. */
  kind: string;
  /** The resource this control is about. */
  uid: string;
  enabled: boolean;
  /** Pre-fetched scope from a list payload (`null` = everywhere). Omit it to
   *  let the control fetch its own; `undefined` is "not supplied", never a
   *  value. */
  scope?: Scope | null;
  /** Whether this KIND declares a per-agent scope at all. Only a prefetching
   *  caller has to say: it skips the query that would have answered, and
   *  `false` there collapses the panel to Disabled/Enabled. A caller that lets
   *  the control fetch gets the server's answer and can leave this alone. */
  supportsScope?: boolean;
}

export function ScopeControl({
  kind,
  uid,
  enabled,
  scope: presetScope,
  supportsScope: kindSupportsScope = true,
}: Props) {
  const { t } = useTranslation();
  const prefetched = presetScope !== undefined;
  const { data: fetchedScope } = useResourceScope(uid, !prefetched);
  const scopeData: ResourceScope | undefined = prefetched
    ? {
        // No scope declared means no scope to report, whatever the row still
        // carries from when the kind had one.
        scope: kindSupportsScope ? presetScope : null,
        supports_scope: kindSupportsScope,
      }
    : fetchedScope;
  const { data: agentsData } = useAgents();
  const update = useUpdateResourceScope(kind, uid);
  const enable = useEnableResource();
  const disable = useDisableResource();

  const busy = update.isPending || enable.isPending || disable.isPending;
  // While the scope query is in flight, assume the kind supports scope; the
  // fallback only matters once the server has said otherwise.
  const supportsScope = scopeData ? scopeData.supports_scope : true;
  const scope = scopeData?.scope ?? null;

  const mode: ReachMode = reachModeOf({ enabled, scope });

  const enableIfNeeded = () => {
    if (!enabled) enable.mutate({ kind, uid });
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
  //
  // But NOT on a disabled resource. There the button already says "Disabled",
  // which is the whole reason it reaches nobody; colouring it amber over the
  // scope underneath answers a question the label just answered, with a second
  // answer the reader cannot act on — turning the resource back on is the only
  // move, and the scope only starts mattering once they do. Two rows both
  // reading "Disabled" in two different colours is the symptom.
  const note =
    mode !== "disabled" &&
    isDormantHere(
      scope,
      (agentsData ?? []).map((a) => a.uid),
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
      onDisabled={() => disable.mutate({ kind, uid })}
      onEverywhere={() => {
        enableIfNeeded();
        if (scope !== null) update.mutate(null);
      }}
      onRestricted={commitScope}
    />
  );
}
