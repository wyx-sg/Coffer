// frontend/src/components/agents/AgentSelect.tsx
//
// "Which agent?", as a single choice. It offers agent NAMES and hands back an
// agent UID.
//
// That asymmetry is the whole component. Every stored reference to an agent —
// a channel's `default_agent`, a resource scope's agent list, a skill binding —
// holds the uid, because a reference has to keep pointing at the same agent
// after the owner relabels it (ADR resource-identity-is-an-immutable-uid). A
// uid is also the one thing a person cannot read. So every surface that binds
// an agent faces the same two-sided problem, and solving it once here is what
// stops each of them solving it slightly differently.
//
// `AgentPicker` (components/reach) is the same problem in its multi-select
// form, under the reach control's "only selected agents". The two are separate
// components because one is a Radix Select and the other a list of checkboxes
// with its own dormant/unknown vocabulary — but they agree on the rule, and a
// change to the rule has to land in both.
//
// A value no registered agent answers to is KEPT and shown as itself, never
// dropped. Dropping it would silently re-bind whatever holds it to whichever
// agent happens to sort first; showing the uid at least tells the owner what
// the binding actually says, which is the only thing that lets them fix it.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgents } from "@/lib/hooks/useAgents";

interface Props {
  /** Ties the control to its own <Label>. */
  id?: string;
  /** The control's accessible name. */
  label: string;
  /** The chosen agent's uid; `""` is nothing chosen. */
  value: string;
  onChange: (agentUid: string) => void;
  disabled?: boolean;
}

export function AgentSelect({ id, label, value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const { data: agents } = useAgents();

  const known = (agents ?? []).map((a) => ({ uid: a.uid, name: a.name }));
  // A stored uid this vault has no agent for still gets an option, labelled
  // with the uid itself — there is no name to print, and printing nothing
  // would hide the binding rather than report it.
  const options =
    value !== "" && !known.some((a) => a.uid === value)
      ? [...known, { uid: value, name: value }]
      : known;

  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger id={id} aria-label={label}>
        <SelectValue placeholder={t("common.emptyValue")} />
      </SelectTrigger>
      <SelectContent>
        {options.map((a) => (
          <SelectItem key={a.uid} value={a.uid}>
            {a.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
