// src/components/custom-tools/DraftReachField.tsx — a reach chosen inside a form and written with it.
//
// The page's ScopeControl writes as soon as its panel closes; a form's reach
// is part of the draft it saves. So this is the same button and panel
// vocabulary (ReachButton over "every agent" / "only selected agents" and the
// agent checklist) without a write of its own: `null` is every agent, a list
// of agent uids the narrowed reach. `pickOnly` drops the two choices and
// leaves the checklist — a tool's own reach, where "the group's default" is
// the segmented choice beside it (ToolReachField).
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentPicker } from "@/components/reach/AgentPicker";
import { ReachButton } from "@/components/reach/ReachButton";
import { ReachChoice } from "@/components/reach/ReachChoice";
import { chosenAgents, pickableAgents, reachLabel } from "@/components/reach/reachState";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgents } from "@/lib/hooks/useAgents";

interface Props {
  value: string[] | null;
  onChange: (value: string[] | null) => void;
  /** Only the agent checklist (the value is always a list). */
  pickOnly?: boolean;
  disabled?: boolean;
  id?: string;
}

export function DraftReachField({ value, onChange, pickOnly = false, disabled, id }: Props) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();
  const [open, setOpen] = useState(false);
  const group = useId();
  const registered = pickableAgents(agents);
  const selected = value ?? [];
  const restricted = value !== null;
  const scope = restricted ? { agents: selected } : null;
  const live = restricted ? "restricted" : "everywhere";
  const total = registered.length;
  const label =
    restricted && total > 0
      ? t("customTools.reach.countOf", { count: selected.length, total })
      : reachLabel(t, live, scope);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <ReachButton
          id={id}
          live={live}
          label={label}
          chosen={chosenAgents(scope, registered)}
          disabled={disabled}
          className="w-fit"
        />
      </PopoverTrigger>
      <PopoverContent align="start" className="flex w-[316px] flex-col gap-2.5 p-3 text-text">
        <p className="text-xs font-semibold text-text">{t("scope.availableTo")}</p>
        {pickOnly ? null : (
          <div
            role="radiogroup"
            aria-label={t("scope.choicesLabel")}
            className="border-b border-border-subtle pb-2.5"
          >
            <ReachChoice
              group={group}
              checked={!restricted}
              disabled={Boolean(disabled)}
              text={t("scope.everywhere")}
              sub={t("scope.everywhereSub")}
              onPick={() => {
                onChange(null);
                setOpen(false);
              }}
            />
            <ReachChoice
              group={group}
              checked={restricted}
              disabled={Boolean(disabled)}
              text={t("scope.restricted")}
              sub={t("scope.restrictedSub")}
              onPick={() => onChange(selected)}
            />
          </div>
        )}
        <AgentPicker
          registered={registered}
          selected={selected}
          dormant={restricted && selected.length === 0}
          busy={Boolean(disabled)}
          onToggle={(uid, checked) =>
            onChange(checked ? [...selected, uid] : selected.filter((entry) => entry !== uid))
          }
        />
      </PopoverContent>
    </Popover>
  );
}
