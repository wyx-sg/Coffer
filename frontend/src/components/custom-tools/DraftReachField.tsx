// src/components/custom-tools/DraftReachField.tsx — a reach chosen inside a form and written with it.
//
// The page's ScopeControl writes as soon as its panel closes; a form's reach
// is part of the draft it saves. So this is the same vocabulary (a radio for
// "every agent" — or, for one tool, "the group's default" — and one for "only
// selected agents" over the agent checklist) without a write of its own:
// `null` is the first choice, a list of agent uids the second.
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { AgentPicker } from "@/components/reach/AgentPicker";
import { ReachChoice } from "@/components/reach/ReachChoice";
import { pickableAgents } from "@/components/reach/reachState";
import { useAgents } from "@/lib/hooks/useAgents";

interface Props {
  value: string[] | null;
  onChange: (value: string[] | null) => void;
  /** The first choice's title and sub line ("Every agent", "Group default"). */
  defaultLabel: string;
  defaultSub: string;
  disabled?: boolean;
}

export function DraftReachField({ value, onChange, defaultLabel, defaultSub, disabled }: Props) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();
  const group = useId();
  const selected = value ?? [];
  const restricted = value !== null;
  return (
    <div role="radiogroup" aria-label={t("scope.choicesLabel")} className="space-y-1">
      <ReachChoice
        group={group}
        checked={!restricted}
        disabled={Boolean(disabled)}
        text={defaultLabel}
        sub={defaultSub}
        onPick={() => onChange(null)}
      />
      <ReachChoice
        group={group}
        checked={restricted}
        disabled={Boolean(disabled)}
        text={t("scope.restricted")}
        sub={t("scope.restrictedSub")}
        onPick={() => onChange(selected)}
      />
      {restricted ? (
        <AgentPicker
          className="pl-6"
          registered={pickableAgents(agents)}
          selected={selected}
          dormant={selected.length === 0}
          busy={Boolean(disabled)}
          onToggle={(uid, checked) =>
            onChange(checked ? [...selected, uid] : selected.filter((entry) => entry !== uid))
          }
        />
      ) : null}
    </div>
  );
}
