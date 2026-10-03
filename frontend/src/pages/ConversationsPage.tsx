// pages/ConversationsPage.tsx — spec chat "Show every conversation on the
// Conversations page". `/conversations` is the list of every conversation Coffer
// runs, whatever opened it, with source and agent filters in the URL;
// `/conversations/:id` opens one full width (and `/conversations/new` the draft
// New conversation opens), each with a back link to the list. Orchestration lives in useChatController; the
// two layouts are ConversationsIndex and ConversationWorkspace.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { ConversationsIndex } from "@/components/chat/ConversationsIndex";
import { ConversationWorkspace } from "@/components/chat/ConversationWorkspace";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { agentTypeLabel } from "@/lib/agents/display";
import { channelSource } from "@/lib/conversations/filters";
import { useChannels } from "@/lib/hooks/useChannels";
import { useChatController } from "@/lib/hooks/useChatController";
import { displayName } from "@/lib/resourceTitle";

export function ConversationsPage() {
  const { t } = useTranslation();
  const c = useChatController();
  const { data: channels } = useChannels();

  const agentNames = useMemo(
    () => new Map(c.agents.map((a) => [a.agent_key, a.display_name])),
    [c.agents],
  );
  const channel = c.filters.channel
    ? channels?.find((r) => r.uid === c.filters.channel)
    : undefined;
  const deletingKey = c.deletingConversation?.agent_key ?? "";
  const deletingAgent = agentNames.get(deletingKey) ?? agentTypeLabel(deletingKey);
  const workspace = c.isDraft || !!c.routeId;

  return (
    <>
      {workspace ? (
        // Full-bleed: Layout pads every page, and a conversation is a workspace
        // whose thread scrolls on its own.
        <div className="relative -mx-6 -my-10 flex h-screen overflow-hidden md:-mx-10">
          <ConversationWorkspace c={c} onNew={c.openDraft} agentNames={agentNames} />
        </div>
      ) : (
        <ConversationsIndex
          c={c}
          onNew={c.openDraft}
          agentNames={agentNames}
          channelLabel={channel ? displayName(channel) : null}
          channelSource={channelSource(channel?.config)}
        />
      )}

      {/* Only Coffer's copy goes: the agent's own files and session stay. */}
      <ConfirmDialog
        open={c.deletingId !== null}
        onOpenChange={(o) => !o && c.requestDelete(null)}
        title={t("conversations.delete.title")}
        description={t("conversations.delete.body", {
          title: c.deletingConversation?.title ?? "",
          agent: deletingAgent,
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
