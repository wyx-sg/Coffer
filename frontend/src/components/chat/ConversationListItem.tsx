// components/chat/ConversationListItem.tsx
// One row of the list beside an open conversation: its title (with a Running
// mark), where it came from, its agent and the time of its last activity. The
// whole row is the link that opens it; rename, archive and delete live in the
// open conversation's header menu, so a row carries no controls of its own.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { StatusDot } from "@/components/status/StatusDot";
import type { Conversation } from "@/lib/api/chat";
import { clock } from "@/lib/conversations/time";
import { cn } from "@/lib/utils";
import { SourceBadge } from "./SourceBadge";

interface Props {
  conversation: Conversation;
  isActive: boolean;
  href: string;
  agentName?: string;
}

export function ConversationListItem({ conversation, isActive, href, agentName }: Props) {
  const { t } = useTranslation();
  return (
    <li>
      <Link
        to={href}
        aria-current={isActive ? "page" : undefined}
        data-conversation={conversation.id}
        className={cn(
          "block space-y-1 rounded-md px-2.5 py-2 outline-none transition-colors duration-fast",
          "focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
          isActive ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          {conversation.running ? (
            <span className="shrink-0">
              <StatusDot tone="ok" />
              <span className="sr-only">{t("conversations.list.running")}</span>
            </span>
          ) : null}
          <span className="min-w-0 flex-1 truncate text-sm font-medium text-text">
            {conversation.title}
          </span>
          <time
            dateTime={conversation.updated_at}
            className="shrink-0 font-mono text-2xs text-text-subtle"
          >
            {clock(conversation.updated_at)}
          </time>
        </span>
        <span className="flex min-w-0 items-center gap-2">
          <SourceBadge conversation={conversation} className="min-w-0 flex-1 text-text-muted" />
          <AgentBadge
            type={conversation.agent_key}
            name={agentName}
            size="sm"
            tooltip={!!agentName}
          />
        </span>
      </Link>
    </li>
  );
}
