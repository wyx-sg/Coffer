// src/components/handoff/useAgentHandoff.tsx — the two hand-off verbs, for a surface that lays them out itself.
//
// `AgentHandoff` renders them as one split button; a dense surface with no room for
// two (an Overview "Needs you" row) puts them in its ⋯ menu instead. Either
// way the verbs are the same: copy the daemon's prompt as given, or open the
// draft (New conversation) with the prompt in its composer —
// never sent until the person presses Send. `canAsk` is false while no managed
// agent is available, and the caller then offers Copy prompt only.
import { useNavigate } from "react-router-dom";

import { defaultDraftAgent } from "@/lib/conversations/draftMemory";
import { openHandoffDraft } from "@/lib/conversations/handoff";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useCopyText } from "@/lib/hooks/useCopyText";

export interface AgentHandoffControls {
  copy: () => void;
  /** Whether a managed agent is available to ask. */
  canAsk: boolean;
  /** Open the draft with the prompt typed in, on the default agent. */
  ask: () => void;
}

export function useAgentHandoff(prompt: string): AgentHandoffControls {
  const navigate = useNavigate();
  const { copy } = useCopyText();
  const { data: agents = [] } = useAgentProviders();
  const agentKey = defaultDraftAgent(agents);
  return {
    copy: () => copy(prompt),
    canAsk: agentKey !== "",
    ask: () => openHandoffDraft(navigate, { agentKey, cwd: null, prompt }),
  };
}
