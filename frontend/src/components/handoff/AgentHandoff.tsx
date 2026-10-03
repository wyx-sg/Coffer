// src/components/handoff/AgentHandoff.tsx — hand an environment-dependent chore to an agent.
//
// Coffer does not run open-ended chores (installing, setting up, fixing) on
// this machine itself; it hands the backend's prompt (a `handoff: {prompt}`
// field) to the person's agent, which picks the right way here. One split
// button, [Ask an agent ▾] (AskAgentButton, Foundations 0.7.04): the main half
// opens the draft New conversation with the prompt in its composer, the ▾ menu
// copies the prompt for an agent outside Coffer — then the "?" saying why
// Coffer hands it off. Nothing is sent until the person presses Send. Knows
// nothing about what the chore is: the caller passes the prompt.
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { AskAgentButton } from "./AskAgentButton";

interface Props {
  /** The backend's hand-off text, passed on as is — never assembled by the caller. */
  prompt: string;
  size?: "sm" | "default";
}

export function AgentHandoff({ prompt, size = "default" }: Props) {
  const { t } = useTranslation();
  return (
    <div className="inline-flex items-center gap-2">
      <AskAgentButton prompt={prompt} size={size} />
      <HelpTip>
        <p className="text-xs">{t("handoff.help")}</p>
      </HelpTip>
    </div>
  );
}
