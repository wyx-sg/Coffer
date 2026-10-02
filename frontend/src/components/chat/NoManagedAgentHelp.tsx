// src/components/chat/NoManagedAgentHelp.tsx — what a conversation surface says when no managed agent can run.
//
// Spec chat "Create the conversation on the first send": with no managed agent
// available, the draft and the New conversation dialog say how to get one.
// While no supported agent is installed on this machine the daemon writes the
// prompt that hands installing one to an assistant (GET /agents/types
// `install_handoff`); it is offered to copy only, because there is no agent of
// Coffer's to ask. Once one is installed, adding it is Coffer's own action, so
// the surface links to the Agents page instead. Rendered by the New
// conversation dialog, which `useAgentHandoff` itself opens — hence a plain
// copy button here rather than `AgentHandoff`.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bot, Check, Copy, MessageSquareOff } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { useAgentInstallHandoff } from "@/lib/hooks/useAgentTypes";
import { useCopyText } from "@/lib/hooks/useCopyText";

interface Props {
  /** `empty`: the draft's whole-surface state; `inline`: a paragraph in a dialog. */
  layout: "empty" | "inline";
}

export function NoManagedAgentHelp({ layout }: Props) {
  const { t } = useTranslation();
  // Two states, told apart by the daemon: it writes the install prompt only
  // while NO supported agent is installed on this machine. Once one is installed
  // but not added (or disabled) there is no prompt and adding it is Coffer's own
  // action, so the surface links to the Agents page.
  const handoff = useAgentInstallHandoff();
  const prompt = handoff.data ?? null;
  const { copied, copy } = useCopyText();

  // Not yet known which of the two states this is: say nothing rather than guess.
  if (handoff.isPending) return null;

  const description = t(
    prompt ? "conversations.draft.noAgentInstall" : "conversations.draft.noAgentAdd",
  );
  const action = prompt ? (
    <Button type="button" variant="outline" size="sm" onClick={() => copy(prompt)}>
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      {copied ? t("handoff.copied") : t("handoff.copyPrompt")}
    </Button>
  ) : (
    <Button variant="outline" size="sm" asChild>
      <Link to="/agents">
        <Bot aria-hidden />
        {t("conversations.draft.openAgents")}
      </Link>
    </Button>
  );

  if (layout === "empty") {
    return (
      <EmptyState
        className="flex-1"
        icon={MessageSquareOff}
        title={t("conversations.draft.noAgentTitle")}
        description={description}
        action={action}
      />
    );
  }
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-sm text-text-muted">{description}</p>
      {action}
    </div>
  );
}
