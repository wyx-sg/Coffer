// pages/ConversationsPage.tsx — spec chat "Show every conversation on the
// Conversations page". `/conversations` is the list of every conversation Coffer
// runs, whatever opened it, with source and agent filters in the URL;
// `/conversations/:id` opens one full width (and `/conversations/new` the draft
// New conversation opens); its title row sits in the window title bar and there
// is no back link (the title bar's ← does that). Orchestration lives in useChatController; the
// two layouts are ConversationsIndex and ConversationWorkspace.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { ConversationsIndex } from "@/components/chat/ConversationsIndex";
import { ConversationWorkspace } from "@/components/chat/ConversationWorkspace";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useChatController } from "@/lib/hooks/useChatController";
import { PAGE_BLEED } from "@/components/shell/pageFrame";
import { cn } from "@/lib/utils";

export function ConversationsPage() {
  const { t } = useTranslation();
  const c = useChatController();

  const agentNames = useMemo(
    () => new Map(c.agents.map((a) => [a.agent_key, a.display_name])),
    [c.agents],
  );
  const workspace = c.isDraft || !!c.routeId;

  return (
    <>
      {workspace ? (
        // Full-bleed: Layout pads every page (32px sides, 16 above, 40 below), and a
        // conversation is a workspace whose thread scrolls on its own.
        <div className={cn(PAGE_BLEED, "relative")}>
          <ConversationWorkspace c={c} onNew={c.openDraft} agentNames={agentNames} />
        </div>
      ) : (
        <ConversationsIndex c={c} onNew={c.openDraft} agentNames={agentNames} />
      )}

      {/* Only Coffer's copy goes: the agent's own files and session stay. */}
      <ConfirmDialog
        open={c.deletingId !== null}
        onOpenChange={(o) => !o && c.requestDelete(null)}
        title={t("conversations.delete.title", { title: c.deletingConversation?.title ?? "" })}
        description={t("conversations.delete.body", {
          title: c.deletingConversation?.title ?? "",
        })}
        confirmLabel={t("conversations.delete.confirm")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteConversation")}
        pending={c.deletePending}
        onConfirm={c.confirmDelete}
      />
    </>
  );
}
