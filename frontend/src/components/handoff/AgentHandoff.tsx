// src/components/handoff/AgentHandoff.tsx — hand an environment-dependent chore to an agent.
//
// Coffer does not run open-ended chores (installing, setting up, fixing) on
// this machine itself; it hands the backend's prompt (a `handoff: {prompt}`
// field) to the person's agent, which picks the right way here. Two buttons:
// Copy prompt, for any agent, and Ask an agent, which opens the New
// conversation dialog (agent and folder) and then the draft with the prompt in
// its composer (lib/conversations/handoff.ts). Nothing is sent until the person
// presses Send — managed agents run with full permissions. With no managed
// agent available only Copy prompt is offered. Knows nothing about what the
// chore is: the caller passes the prompt.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Copy, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { NewConversationDialog } from "@/components/chat/NewConversationDialog";
import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { openHandoffDraft } from "@/lib/conversations/handoff";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useCopyText } from "@/lib/hooks/useCopyText";

interface Props {
  /** The backend's hand-off text, passed on as is — never assembled by the caller. */
  prompt: string;
  size?: "sm" | "default";
}

export function AgentHandoff({ prompt, size = "default" }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { copied, copy } = useCopyText();
  const { data: agents = [] } = useAgentProviders();
  const [choosing, setChoosing] = useState(false);
  const canAsk = agents.some((a) => a.available);

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" size={size} onClick={() => copy(prompt)}>
        {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        {copied ? t("handoff.copied") : t("handoff.copyPrompt")}
      </Button>
      {canAsk ? (
        <>
          <Button type="button" variant="outline" size={size} onClick={() => setChoosing(true)}>
            <MessageSquarePlus aria-hidden />
            {t("handoff.askAgent")}
          </Button>
          <NewConversationDialog
            open={choosing}
            onOpenChange={setChoosing}
            agents={agents}
            onStart={(config) => openHandoffDraft(navigate, { ...config, prompt })}
          />
        </>
      ) : null}
      <HelpTip>
        <p className="text-xs">{t("handoff.help")}</p>
      </HelpTip>
    </div>
  );
}
