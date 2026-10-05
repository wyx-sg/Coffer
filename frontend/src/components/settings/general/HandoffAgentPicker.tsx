// frontend/src/components/settings/general/HandoffAgentPicker.tsx
//
// Settings › General: the agent a hand-off starts, among the managed ones.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AgentOption } from "@/components/agent/AgentOption";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { getHandoffAgent, type HandoffAgent, useSetHandoffAgent } from "@/lib/preferences";

/** The agents a hand-off can start, in the order the setting lists them. */
const HANDOFF_AGENTS: readonly HandoffAgent[] = ["claude_code", "codex"];

export function HandoffAgentPicker() {
  const { t } = useTranslation();
  const setHandoffAgent = useSetHandoffAgent();
  const { data: agents = [] } = useAgentProviders();
  const [stored, setStored] = useState(getHandoffAgent);

  const managed = HANDOFF_AGENTS.flatMap((key) => {
    const found = agents.find((a) => a.agent_key === key && a.available);
    return found ? [{ key, name: found.display_name }] : [];
  });
  if (managed.length === 0) {
    return <p className="w-56 text-xs text-text-muted">{t("settings.general.handoffAgentNone")}</p>;
  }
  // A stored agent that is not managed reads as the first managed one, as a hand-off does.
  const value = managed.find((a) => a.key === stored)?.key ?? managed[0].key;
  return (
    <Select
      value={value}
      onValueChange={(next) => {
        setStored(next as HandoffAgent);
        setHandoffAgent(next as HandoffAgent);
      }}
    >
      <SelectTrigger className="w-56" aria-label={t("settings.general.handoffAgent")}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {managed.map((a) => (
          <SelectItem key={a.key} value={a.key}>
            <AgentOption type={a.key} name={a.name} />
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
