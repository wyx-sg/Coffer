// src/components/handoff/useAgentHandoff.tsx — the two hand-off verbs behind `AgentHandoff`.
//
// Every hand-off in the app is the `AgentHandoff` split button; this hook is
// its logic. The verbs: copy the daemon's prompt as given (a "Prompt
// copied" toast says so), or open the draft (New conversation) with the prompt
// in its composer — never sent until the person presses Send. `canAsk` is false
// while no managed agent is available, and the caller then offers Copy prompt only.
//
// The prompt may also be a function: a hand-off that is a request in itself
// (it records the files as handed over) is made only when the person picks a
// verb, and is told which agent the draft opens on (null for Copy prompt).
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/components/ui/toast";
import { defaultDraftAgent } from "@/lib/conversations/draftMemory";
import { openHandoffDraft } from "@/lib/conversations/handoff";
import { translateApiError } from "@/lib/api/errors";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";

/** The hand-off text, or a request for it made when a verb is picked. */
export type PromptSource = string | ((target: { agent: string | null }) => Promise<string>);

export interface AgentHandoffControls {
  copy: () => void;
  /** Whether a managed agent is available to ask. */
  canAsk: boolean;
  /** Open the draft with the prompt typed in, on the default agent. */
  ask: () => void;
}

export function useAgentHandoff(prompt: PromptSource): AgentHandoffControls {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const { data: agents = [] } = useAgentProviders();
  const agentKey = defaultDraftAgent(agents);
  const agentName = agents.find((a) => a.agent_key === agentKey)?.display_name ?? null;
  const failed = (error: unknown) => toast.error(translateApiError(t, error));
  const copied = (text: string) => {
    void navigator.clipboard?.writeText(text).then(() => toast.success(t("handoff.promptCopied")));
  };
  const opened = (text: string) =>
    openHandoffDraft(navigate, { agentKey, cwd: null, prompt: text });
  // A plain prompt acts at once, inside the click; a requested one when it arrives.
  const run = (agent: string | null, then: (text: string) => void) => {
    if (typeof prompt === "string") then(prompt);
    else void prompt({ agent }).then(then).catch(failed);
  };
  return {
    copy: () => run(null, copied),
    canAsk: agentKey !== "",
    ask: () => run(agentName, opened),
  };
}
