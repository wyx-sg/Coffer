// pages/ConversationsPage.tsx — spec chat "Show every conversation on the
// Conversations page". `/conversations` is the list of every conversation Coffer
// runs, whatever opened it, with source and agent filters in the URL;
// `/conversations/:id` opens one beside that list (and `/conversations/new` the
// draft New conversation starts). Orchestration lives in useChatController; the
// two layouts are ConversationsIndex and ConversationWorkspace.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConversationsIndex } from "@/components/chat/ConversationsIndex";
import { ConversationWorkspace } from "@/components/chat/ConversationWorkspace";
import { NewConversationDialog } from "@/components/chat/NewConversationDialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { agentTypeLabel } from "@/lib/agents/display";
import { channelSource } from "@/lib/conversations/filters";
import { useChannels } from "@/lib/hooks/useChannels";
import { useChatController } from "@/lib/hooks/useChatController";
import { displayName } from "@/lib/resourceTitle";

export function ConversationsPage() {
  const { t } = useTranslation();
  const c = useChatController();
  const [newOpen, setNewOpen] = useState(false);
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
  const openNew = () => setNewOpen(true);
  const workspace = c.isDraft || !!c.routeId;

  return (
    <>
      {workspace ? (
        // Full-bleed: Layout pads every page, and a conversation is a workspace
        // whose list and thread each scroll on their own.
        <div className="relative -mx-6 -my-10 flex h-screen overflow-hidden md:-mx-10">
          <ConversationWorkspace c={c} onNew={openNew} agentNames={agentNames} />
        </div>
      ) : (
        <ConversationsIndex
          c={c}
          onNew={openNew}
          agentNames={agentNames}
          channelLabel={channel ? displayName(channel) : null}
          channelSource={channelSource(channel?.config)}
        />
      )}

      <NewConversationDialog
        open={newOpen}
        onOpenChange={setNewOpen}
        agents={c.agents}
        onStart={c.startDraft}
      />

      {/* Only Coffer's copy goes: the agent's own files and session stay. */}
      <ConfirmDialog
        open={c.deletingId !== null}
        onOpenChange={(o) => !o && c.requestDelete(null)}
        title={t("conversations.delete.title")}
        description={t("conversations.delete.body", {
          title: c.deletingConversation?.title ?? "",
          agent: deletingAgent,
        })}
        confirmLabel={c.deletePending ? t("common.deleting") : t("conversations.delete.confirm")}
        pending={c.deletePending}
        onConfirm={c.confirmDelete}
      />
    </>
  );
}
