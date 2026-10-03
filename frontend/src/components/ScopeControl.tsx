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
// that is set.
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
// Mutation pattern: ReachControl saves every change AT ONCE — each mode switch
// and each tick is one call here, in order, and the promise it gets back drives
// its Saving… / Saved / Couldn't save line (the hooks run `quiet`, so a failed
// write is shown inline in the panel, never as a toast):
//   - "Off" posts .../disable and writes no scope.
//   - "All agents" enables if needed and writes `null`.
//   - "Chosen agents" (a switch, or a tick) enables if needed and writes the
//     whole list, unless it equals what is stored. It is always a list:
//     relaxing back to all agents is the "All agents" choice above, so the same
//     state can never arrive here under a second name.
// What the resource currently holds is tracked in a ref beside the props,
// because two writes queued back to back must each be judged against the one
// before it, not against props that have not refetched yet.
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
// Every kind that mounts this control declares a per-agent scope. The fetched
// `/scope` answer still carries `supports_scope`, but it is deliberately
// ignored here: the kinds that answer `false` (agent, knowledge, memory) have
// no reach control on any page, so no mounted instance can receive it.
import { useRef } from "react";
import { useTranslation } from "react-i18next";

import { ReachControl } from "@/components/reach/ReachControl";
import { reachModeOf, type ReachMode } from "@/lib/reach/reachState";
import { useAgents } from "@/lib/hooks/useAgents";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";
import { useResourceScope, useUpdateResourceScope, type Scope } from "@/lib/hooks/useScope";
import { isDormantHere, sameScope } from "@/lib/scope";

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
  /** The resource's name, shown small under the panel title. */
  resourceName?: string;
}

export function ScopeControl({ kind, uid, enabled, scope: presetScope, resourceName }: Props) {
  const { t } = useTranslation();
  const prefetched = presetScope !== undefined;
  const { data: fetchedScope } = useResourceScope(uid, !prefetched);
  const { data: agentsData } = useAgents();
  const update = useUpdateResourceScope(kind, uid, { quiet: true });
  const enable = useEnableResource({ quiet: true });
  const disable = useDisableResource({ quiet: true });

  const scope = (prefetched ? presetScope : fetchedScope?.scope) ?? null;

  const mode: ReachMode = reachModeOf({ enabled, scope });

  // What the resource holds right now, including writes not yet refetched.
  const held = useRef({ enabled, scope });
  const seen = useRef({ enabled, scope });
  if (seen.current.enabled !== enabled || !sameScope(seen.current.scope, scope)) {
    seen.current = { enabled, scope };
    held.current = { enabled, scope };
  }

  const enableIfNeeded = async () => {
    if (held.current.enabled) return;
    await enable.mutateAsync({ kind, uid });
    held.current.enabled = true;
  };

  const writeScope = async (next: Scope | null) => {
    if (sameScope(held.current.scope, next)) return;
    await update.mutateAsync(next);
    held.current.scope = next;
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
  // But NOT on a disabled resource. There the button already says "Off",
  // which is the whole reason it reaches nobody; colouring it amber over the
  // scope underneath answers a question the label just answered, with a second
  // answer the reader cannot act on — turning the resource back on is the only
  // move, and the scope only starts mattering once they do. Two rows both
  // reading "Off" in two different colours is the symptom.
  //
  // An EMPTY list gets no note: its button already reads "No agent" (muted),
  // and an amber second answer to the same question is noise.
  const note =
    mode !== "disabled" &&
    (scope?.agents?.length ?? 0) > 0 &&
    isDormantHere(
      scope,
      (agentsData ?? []).map((a) => a.uid),
    )
      ? t("scope.inactiveHereAgent")
      : undefined;

  return (
    <ReachControl
      mode={mode}
      initialScope={scope}
      note={note}
      resourceName={resourceName}
      onDisabled={async () => {
        await disable.mutateAsync({ kind, uid });
        held.current.enabled = false;
      }}
      onEverywhere={async () => {
        await enableIfNeeded();
        await writeScope(null);
      }}
      onRestricted={async (staged) => {
        await enableIfNeeded();
        await writeScope(staged);
      }}
    />
  );
}
