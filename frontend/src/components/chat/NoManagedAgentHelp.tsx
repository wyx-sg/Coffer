// src/components/chat/NoManagedAgentHelp.tsx — what the draft says when no managed agent can run.
//
// Spec chat "Create the conversation on the first send": with no managed agent
// available, the draft is replaced by this state, with a way to the Agents page
// — where connecting one is Coffer's own action. It carries no install prompt:
// handing an install to an assistant belongs to the Agents page itself (Run 3.1.23).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { MessageSquareOff } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function NoManagedAgentHelp() {
  const { t } = useTranslation();
  return (
    <EmptyState
      className="flex-1"
      icon={MessageSquareOff}
      title={t("conversations.draft.noAgentTitle")}
      description={t("conversations.draft.noAgentBody")}
      action={
        <Button variant="ghost" size="sm" asChild>
          <Link to="/agents">{t("conversations.draft.openAgents")}</Link>
        </Button>
      }
    />
  );
}
