// src/components/handoff/AgentHandoff.tsx — hand an environment-dependent chore to an agent.
//
// Coffer does not run open-ended chores (installing, setting up, fixing) on
// this machine itself; it hands the backend's prompt (a `handoff: {prompt}`
// field) to the person's agent, which picks the right way here. Two buttons:
// Copy prompt, for any agent, and Ask an agent, which opens the draft
// New conversation with the prompt in its composer (lib/conversations/handoff.ts). Nothing is sent until the person
// presses Send — managed agents run with full permissions. With no managed
// agent available only Copy prompt is offered. Knows nothing about what the
// chore is: the caller passes the prompt.
import { Check, Copy, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { useAgentHandoff } from "./useAgentHandoff";

interface Props {
  /** The backend's hand-off text, passed on as is — never assembled by the caller. */
  prompt: string;
  size?: "sm" | "default";
}

export function AgentHandoff({ prompt, size = "default" }: Props) {
  const { t } = useTranslation();
  const { copied, copy, canAsk, ask } = useAgentHandoff(prompt);

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" size={size} onClick={copy}>
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        {copied ? t("handoff.copied") : t("handoff.copyPrompt")}
      </Button>
      {canAsk ? (
        <Button type="button" variant="outline" size={size} onClick={ask}>
          <MessageSquarePlus aria-hidden />
          {t("handoff.askAgent")}
        </Button>
      ) : null}
      <HelpTip>
        <p className="text-xs">{t("handoff.help")}</p>
      </HelpTip>
    </div>
  );
}
