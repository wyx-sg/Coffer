// frontend/src/components/reach/ReachControl.tsx
//
// The three-way reach choice — Disabled / Everywhere / Restricted… — written
// ONCE, as pure UI. It owns the segment vocabulary (which segments exist, what
// they are called, which one reads as active) and the restriction panel with
// its staged draft; it owns no resource data and fires no request.
//
// Three surfaces render this exact choice and must never drift apart:
//   • ScopeControl        — one resource, in a table row or on a detail page.
//   • BulkReachActions    — the same choice applied to a whole selection.
//   • the two-segment fallback for kinds that declare no scope, which is the
//     same control minus its third segment (`supportsScope={false}`).
// Each of them supplies the three callbacks; none of them re-implements the
// buttons, the labels, or the panel.
//
// "Restricted" names agents, and nothing else. The agent list is a PICK-LIST
// and never free text: a mistyped name matches nothing, which silently makes
// the resource dormant rather than failing. It lives HERE rather than in one
// consumer, so the bulk bar offers exactly what a row offers.
//
// Reach — the `enabled` flag and this scope, together — is MACHINE-LOCAL. It is
// held in this vault and never converged with a remote, so the same skill can
// be live here and disabled on the user's other machine, by design. The panel
// says that out loud, because nothing else the user touches would tell them
// that the choice they are making here does not follow them; a user who assumed
// it did would set reach once and wonder why the other machine ignored it.
//
// Staging, not per-tick writes: the two whole-value segments each already name
// a complete state, so a consumer writes them immediately. A selection is only
// finished when the user stops picking, so the draft lives here and
// `onRestricted` fires exactly once, when the panel closes. (Writing per tick
// refetched the list under the open panel, and the row it is anchored to moved
// out from under it.)
//
// `initialScope` seeds that draft when the panel opens. A single-resource
// consumer passes the resource's current scope, so the panel opens on what is
// stored; the bulk consumer passes nothing, because a bulk write is a new
// intent rather than an edit of any one row's value.
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";
import type { Scope } from "@/lib/hooks/useScope";

/** Which of the three segments reads as the live state. */
export type ReachMode = "disabled" | "everywhere" | "restricted";

/** The segmented-group shell, exported so a consumer that needs the same frame
 *  around something else (a pending placeholder, say) matches it exactly. */
export const REACH_GROUP_CLASS = "flex items-center gap-1 rounded-md border border-border p-0.5";

/** Opening "Restricted" from "Everywhere" starts on an empty list, dormant
 *  until the user picks an agent — the prompt the choice is asking for. */
const RESTRICTED_START: Scope = { agents: [] };

const WARNING_CLASS =
  "rounded border border-status-warn/40 bg-status-warn/5 px-3 py-2 text-xs text-status-warn";

interface Props {
  /** The active segment; `null` marks none of them active — the bulk bar, where
   *  the selection has no single current reach to reflect. */
  mode: ReachMode | null;
  /** `false` collapses the group to Disabled/Enabled for a kind that declares
   *  no scope. */
  supportsScope?: boolean;
  /** Renders every segment inert while a write is in flight. */
  busy?: boolean;
  /** Seed for the draft when the panel opens; `null` is a fresh intent. */
  initialScope?: Scope | null;
  /** Why this resource is inactive *here*, when it is — named by the consumer
   *  that knows the stored scope. The bulk bar passes nothing, since a mixed
   *  selection has no single answer. */
  note?: string;
  onDisabled: () => void;
  onEverywhere: () => void;
  /** Fired once, on panel close, with the whole staged scope. */
  onRestricted: (scope: Scope) => void;
  testId?: string;
  /** Names the group for assistive tech; the bulk bar sets it so the
   *  selection-wide control is distinguishable from the per-row ones. */
  ariaLabel?: string;
}

export function ReachControl({
  mode,
  supportsScope = true,
  busy = false,
  initialScope = null,
  note,
  onDisabled,
  onEverywhere,
  onRestricted,
  testId = "scope-control",
  ariaLabel,
}: Props) {
  const { t } = useTranslation();
  const { data: agentsData } = useAgents();
  // The pick-list's staged selection: `undefined` while the panel is closed.
  const [draft, setDraft] = useState<Scope | undefined>(undefined);

  // Shared look for one segment of the group: the active one is filled, the
  // rest are quiet, and every one of them is inert while a write is in flight.
  //
  // Every segment also carries the machine-local fact as its tooltip, not only
  // the panel below. "Disabled" and "Everywhere" are whole-value writes — they
  // commit on the click and never open the panel — so a user could set a
  // resource's reach for the life of this machine without ever seeing the line
  // that says it stops here.
  const segment = (active: boolean) =>
    ({
      type: "button",
      size: "sm",
      variant: active ? "secondary" : "ghost",
      "aria-pressed": active,
      disabled: busy,
      title: t("scope.machineLocal"),
    }) as const;

  if (!supportsScope) {
    return (
      <div className={REACH_GROUP_CLASS} data-testid={testId} aria-label={ariaLabel}>
        <Button {...segment(mode === "disabled")} onClick={onDisabled}>
          {t("common.disabled")}
        </Button>
        <Button {...segment(mode !== null && mode !== "disabled")} onClick={onEverywhere}>
          {t("common.enabled")}
        </Button>
      </div>
    );
  }

  const staged = draft ?? initialScope ?? RESTRICTED_START;
  const selected = staged.agents ?? [];
  const registered = (agentsData ?? []).map((a) => a.name);
  // Names already in the scope that this vault does not recognise still render
  // — a resource can legally be scoped to an agent that has not been registered
  // here — badged as unknown rather than dropped, which would rewrite the
  // user's scope behind their back.
  const rows = [...registered, ...selected.filter((name) => !registered.includes(name))];
  const dormant = staged.agents?.length === 0;

  // `agents === null` is "every agent", where the selection is empty: ticking a
  // row there hands back a one-entry list, which IS the un-tick of "every
  // agent" — the two states are one value, so they cannot disagree. That is
  // also why the rows stay on screen while "every agent" is ticked: narrowing
  // is one click from where the user already is, rather than un-tick-then-find.
  const toggle = (name: string, checked: boolean) => {
    const base = staged.agents ?? [];
    setDraft({
      agents: checked ? [...base, name] : base.filter((entry) => entry !== name),
    });
  };

  const openList = (open: boolean) => {
    if (open) {
      setDraft(initialScope ?? RESTRICTED_START);
      return;
    }
    const stagedOnClose = draft;
    setDraft(undefined);
    if (stagedOnClose === undefined) return;
    onRestricted(stagedOnClose);
  };

  return (
    <div className={REACH_GROUP_CLASS} data-testid={testId} aria-label={ariaLabel}>
      <Button {...segment(mode === "disabled")} onClick={onDisabled}>
        {t("common.disabled")}
      </Button>
      <Button {...segment(mode === "everywhere")} onClick={onEverywhere}>
        {t("scope.everywhere")}
      </Button>
      <Popover open={draft !== undefined} onOpenChange={openList}>
        <PopoverTrigger asChild>
          <Button
            {...segment(mode === "restricted")}
            // The dormancy note is about THIS resource and is the more urgent
            // of the two, so it wins the tooltip when there is one to show.
            title={note ?? t("scope.machineLocal")}
          >
            {t("scope.restricted")}
            <ChevronDown className="size-3.5" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-96 space-y-3 p-3">
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">{t("scope.subtitle")}</p>
            {/* Quiet, not amber: this is a standing fact about where reach is
                kept, not something wrong with this resource. The amber block
                below is reserved for a scope that currently reaches nobody. */}
            <p className="text-xs text-muted-foreground" data-testid="reach-machine-local">
              {t("scope.machineLocal")}
            </p>
          </div>

          {note ? <p className={WARNING_CLASS}>{note}</p> : null}
          {dormant ? <p className={WARNING_CLASS}>{t("scope.dormant")}</p> : null}

          <div className="space-y-2" data-testid="scope-agent-axis">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t("scope.agentsSection")}
            </p>

            <label className="flex w-full cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={staged.agents === null}
                disabled={busy}
                aria-label={t("scope.everyAgent")}
                onChange={(e) => setDraft({ agents: e.target.checked ? null : [] })}
              />
              <span>{t("scope.everyAgent")}</span>
            </label>

            {rows.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("scope.noAgents")}</p>
            ) : (
              <div className="space-y-1.5">
                {rows.map((name) => (
                  <label
                    key={name}
                    data-testid={`scope-agent-${name}`}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md border border-border/60 p-2 text-sm"
                  >
                    <Checkbox
                      checked={selected.includes(name)}
                      disabled={busy}
                      aria-label={name}
                      onChange={(e) => toggle(name, e.target.checked)}
                    />
                    <span className="min-w-0 flex-1 font-medium">{name}</span>
                    {registered.includes(name) ? null : (
                      <Badge variant="outline">{t("scope.unknownAgent")}</Badge>
                    )}
                  </label>
                ))}
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
