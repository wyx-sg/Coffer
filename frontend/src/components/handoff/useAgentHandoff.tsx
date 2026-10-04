// src/components/handoff/useAgentHandoff.tsx — the hand-off verbs behind `AgentHandoff`.
//
// Every hand-off in the app is the `AgentHandoff` split button; this hook is
// its logic. The verbs: hand the daemon's prompt to an agent — the daemon starts
// it in the person's preferred terminal with the prompt sent, no confirmation —
// or copy the prompt as given for an agent outside Coffer. The default agent is
// the stored hand-off agent while it is managed, else the first managed one
// (Claude Code before Codex); `other` is the second managed agent, offered in
// the menu. With none managed, only Copy prompt exists.
//
// The prompt may also be a function: a hand-off that is a request in itself
// (it records the files as handed over) is made only when the person picks a
// verb, and is told which agent it goes to (null for Copy prompt).
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useAgentProviders } from "@/lib/hooks/useAgentProviders";
import { useOpenInTerminal, useTerminalLabel } from "@/lib/hooks/useTerminals";
import { useHandoffAgentPreference, type HandoffAgent } from "@/lib/preferences";

/** The hand-off text, or a request for it made when a verb is picked. */
export type PromptSource = string | ((target: { agent: string | null }) => Promise<string>);

/** A managed agent a hand-off can start. */
export interface HandoffTarget {
  key: HandoffAgent;
  name: string;
}

export interface AgentHandoffControls {
  /** Copy the prompt as given, with a "Prompt copied" toast. */
  copy: () => void;
  /** The agent the main part starts; null when no agent is managed. */
  agent: HandoffTarget | null;
  /** The other managed agent, offered in the menu. */
  other: HandoffTarget | null;
  /** Start `target` in the preferred terminal with the prompt sent. */
  handoff: (target: HandoffTarget) => void;
  /** The preferred terminal's name, for the tooltip. */
  terminalLabel: string;
}

const ORDER: readonly HandoffAgent[] = ["claude_code", "codex"];

export function useAgentHandoff(prompt: PromptSource): AgentHandoffControls {
  const { t } = useTranslation();
  const { toast } = useToast();
  const openTerminal = useOpenInTerminal();
  const terminalLabel = useTerminalLabel();
  const stored = useHandoffAgentPreference();
  const { data: agents = [] } = useAgentProviders();

  const managed: HandoffTarget[] = ORDER.flatMap((key) => {
    const found = agents.find((a) => a.agent_key === key && a.available);
    return found ? [{ key, name: found.display_name }] : [];
  });
  const agent = managed.find((a) => a.key === stored) ?? managed[0] ?? null;
  const other = managed.find((a) => a.key !== agent?.key) ?? null;

  const failed = (error: unknown) => toast.error(translateApiError(t, error));
  const copied = (text: string) => {
    void navigator.clipboard?.writeText(text).then(() => toast.success(t("handoff.promptCopied")));
  };
  // A plain prompt acts at once, inside the click; a requested one when it arrives.
  const run = (name: string | null, then: (text: string) => void) => {
    if (typeof prompt === "string") then(prompt);
    else void prompt({ agent: name }).then(then).catch(failed);
  };

  return {
    copy: () => run(null, copied),
    agent,
    other,
    terminalLabel,
    handoff: (target) =>
      run(target.name, (text) => {
        void openTerminal(
          { agent: target.key, prompt: text },
          { label: t("handoff.copyPrompt"), onClick: () => copied(text) },
        );
      }),
  };
}
