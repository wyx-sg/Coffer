// src/components/chat/SourceBadge.tsx — where a conversation came from, as the
// Conversations page shows it on every row and above the open thread (spec chat
// "Show every conversation on the Conversations page"): Coffer for one opened in
// Coffer's own UI, else the channel's platform and the place in its chat —
// "SeaTalk · DM · 🧵#2", "SeaTalk · coffer-dev › thread", "Telegram · Personal".
// The channel's own name is the tooltip; it is the badge's text only when the
// chat and thread are not known.
import { useTranslation } from "react-i18next";

import { CofferMark } from "@/components/brand/CofferMark";
import { PlatformMark } from "@/components/channel/PlatformMark";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Conversation } from "@/lib/api/chat";
import { sourceText } from "@/lib/conversations/sourceText";
import { cn } from "@/lib/utils";

interface Props {
  conversation: Conversation;
  className?: string;
}

export function SourceBadge({ conversation, className }: Props) {
  const { t } = useTranslation();
  const binding = conversation.channel_binding;
  const text = sourceText(t, conversation);
  const badge = (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5 whitespace-nowrap text-xs text-text",
        className,
      )}
      data-source={binding ? (binding.platform ?? "channel") : "coffer"}
    >
      {binding ? (
        <PlatformMark platform={binding.platform ?? "channel"} />
      ) : (
        <span className="inline-flex h-[18px] w-[22px] shrink-0 items-center justify-center rounded-sm bg-chip">
          <CofferMark size={12} className="text-text-muted" />
        </span>
      )}
      <span className="truncate">{text}</span>
    </span>
  );
  if (!binding) return badge;
  // A deleted channel keeps its conversations; its uid is then all there is.
  const channel = binding.channel ?? binding.channel_uid;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{badge}</TooltipTrigger>
      <TooltipContent>{t("conversations.source.viaChannel", { channel })}</TooltipContent>
    </Tooltip>
  );
}
