// src/components/handoff/AgentHandoff.tsx — hand an environment-dependent chore to an agent.
//
// Coffer does not run open-ended chores (installing, setting up, fixing) on
// this machine itself; it hands the backend's prompt (a `handoff: {prompt}`
// field) to the person's agent, which picks the right way here. One split
// button (Foundations 0.7.04): the main part, Hand off to <Agent>, asks the
// daemon to start the hand-off agent (Settings › General) in the preferred
// terminal with the prompt sent — no confirmation, a toast says the terminal
// opened, and a refusal offers Copy prompt as the way out. The ▾ menu holds
// Hand off to <other agent> (which then becomes the hand-off agent, so labels follow) when that agent is managed too, then Copy prompt
// ("Prompt copied"), for an agent outside Coffer. With no managed agent only a
// Copy prompt button is offered. A `description` puts a one-line muted note on the
// left of a row the button would otherwise stand alone in. A button given a `label` (Tidy, Tidy all) keeps
// its own name on the main part. Knows nothing about what the chore is: the
// caller passes the prompt.
import { Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentMark } from "@/components/agent/AgentMark";
import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import type { MenuAction } from "@/components/ui/menu";
import { SplitButton } from "@/components/ui/split-button";
import { useSetHandoffAgent } from "@/lib/preferences";
import { useAgentHandoff, type HandoffTarget, type PromptSource } from "./useAgentHandoff";

interface Props {
  /** The backend's hand-off text, passed on as is — never assembled by the caller;
   *  or a request for it, made when the person picks a verb. */
  prompt: PromptSource;
  /** `lg` beside the other controls of a full-page state. */
  size?: "sm" | "default" | "lg";
  /** The "?" beside it; off in a row that already says what the problem is
   *  (Knowledge and Memory failures, after their own Retry / Check again). */
  help?: boolean;
  /** Name the main part ("Tidy") instead of "Hand off to <Agent>"; a function
   *  is given the agent's name ("Hand off to <Agent> to restore"). */
  label?: string | ((agent: string) => string);
  /** A one-line muted note on the left of a row the button stands alone in; it is
   *  given the agent's name, or null when only Copy prompt is on offer. */
  description?: (agent: string | null) => string;
}

/** The agent's mark in a button-sized box (a Blossom is bigger than its box; it overflows evenly). */
function Mark({ target }: { target: HandoffTarget }) {
  return (
    <span aria-hidden className="inline-flex size-3.5 shrink-0 items-center justify-center">
      <AgentMark type={target.key} markSize={14} blossomSize={22} />
    </span>
  );
}

export function AgentHandoff({ prompt, size = "default", help = true, label, description }: Props) {
  const { t } = useTranslation();
  const { copy, agent, other, handoff, terminalLabel } = useAgentHandoff(prompt);
  const setDefault = useSetHandoffAgent();

  const actions: MenuAction[] = [];
  if (other) {
    actions.push({
      key: "other",
      label: t("handoff.handoffTo", { agent: other.name }),
      description: t("handoff.handoffToHint", { terminal: terminalLabel }),
      onSelect: () => {
        // The pick becomes the hand-off agent, so every label follows it.
        setDefault(other.key);
        handoff(other);
      },
    });
  }
  actions.push({
    key: "copy",
    label: t("handoff.copyPrompt"),
    description: t("handoff.copyPromptHint"),
    icon: Copy,
    onSelect: copy,
  });

  return (
    <div
      className={
        description
          ? "flex w-full items-center justify-between gap-3"
          : "inline-flex items-center gap-2"
      }
    >
      {description ? (
        <p className="min-w-0 text-xs text-text-muted">{description(agent?.name ?? null)}</p>
      ) : null}
      <div className="inline-flex shrink-0 items-center gap-2">
        {agent ? (
          <SplitButton
            size={size}
            icon={<Mark target={agent} />}
            label={
              typeof label === "function"
                ? label(agent.name)
                : (label ?? t("handoff.handoffTo", { agent: agent.name }))
            }
            tooltip={t("handoff.tooltip", { agent: agent.name, terminal: terminalLabel })}
            onClick={() => handoff(agent)}
            menuLabel={t("handoff.moreOptions")}
            actions={actions}
          />
        ) : (
          <Button type="button" variant="outline" size={size} onClick={copy}>
            <Copy aria-hidden />
            {t("handoff.copyPrompt")}
          </Button>
        )}
        {help ? (
          <HelpTip>
            <p className="text-xs">{t("handoff.help")}</p>
          </HelpTip>
        ) : null}
      </div>
    </div>
  );
}
