// frontend/src/pages/ChatPage.tsx — spec 008-builtin-agent-chat surface.
//
// A master-detail chat experience: the conversation list on the left and the
// active conversation on the right. `/chat` shows the list with an empty-state
// prompt; `/chat/:id` opens that conversation. The new-conversation flow picks
// a target (built-in or managed agent), creates the conversation, and routes to
// it. Actions (rename / archive / restore / delete) live on the list rows and
// the conversation header.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessagesSquare } from "lucide-react";

import { ConversationList } from "@/components/chat/ConversationList";
import { ConversationView } from "@/components/chat/ConversationView";
import { NewConversationDialog } from "@/components/chat/NewConversationDialog";
import type { ConversationStatus } from "@/lib/api/chat";
import { useConversations } from "@/lib/hooks/useChat";

export function ChatPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<ConversationStatus>("active");
  const [newOpen, setNewOpen] = useState(false);

  const { data: conversations, isPending } = useConversations(statusFilter);

  // If the open conversation is filtered out of the list (e.g. archived while
  // viewing the active list), keep it selectable by not forcing a redirect —
  // but if it was deleted we route back to /chat (handled in onDeleted).
  const items = conversations ?? [];

  // Landing on /chat shows the list without auto-selecting; the empty pane
  // prompts the user to pick or start a conversation. Selection is explicit.
  const handleDeleted = (deletedId: string) => {
    if (deletedId === id) navigate("/chat");
  };

  return (
    // Break out of the main content's px-6 py-10 padding and pin the chat
    // surface to the viewport height so the list and transcript each scroll
    // independently. The banner above (if any) sits within the py-10 region.
    <div className="-mx-6 -my-10 flex h-screen md:-mx-10">
      <div className="flex flex-1 overflow-hidden">
        <ConversationList
          conversations={items}
          activeId={id}
          statusFilter={statusFilter}
          isPending={isPending}
          onStatusChange={setStatusFilter}
          onNew={() => setNewOpen(true)}
          onDeleted={handleDeleted}
        />
        {id ? (
          <ConversationView key={id} conversationId={id} />
        ) : (
          <div className="grid flex-1 place-items-center px-6 text-center">
            <div className="max-w-sm space-y-2">
              <MessagesSquare
                className="mx-auto size-10 text-muted-foreground"
                strokeWidth={1.25}
              />
              <h2 className="text-lg font-medium text-foreground">{t("chat.welcome.title")}</h2>
              <p className="text-sm text-muted-foreground">{t("chat.welcome.body")}</p>
            </div>
          </div>
        )}
      </div>

      <NewConversationDialog
        open={newOpen}
        onOpenChange={setNewOpen}
        onCreated={(conversationId) => navigate(`/chat/${conversationId}`)}
      />
    </div>
  );
}
