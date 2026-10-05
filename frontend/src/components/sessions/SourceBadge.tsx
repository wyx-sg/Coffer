// src/components/sessions/SourceBadge.tsx — which channel a conversation came
// from, as the Conversations page and an agent's Sessions tab show it on a row
// (spec chat "Show channel conversations on the Conversations page"): the
// channel's platform logo and the place in its chat — "SeaTalk · DM · Thread 2",
// "SeaTalk · coffer-dev › thread", "Telegram · Personal". The channel's own
// name is the badge's text only when the chat and thread are not known. Long
// text is cut with its full words in a tooltip.
import { useTranslation } from "react-i18next";

import { PlatformMark } from "@/components/channel/PlatformMark";
import { TruncatedText } from "@/components/ui/truncated-text";
import { sourceText } from "@/lib/conversations/sourceText";
import type { SessionChannel } from "@/lib/sessions/rows";
import { cn } from "@/lib/utils";

interface Props {
  channel: SessionChannel;
  className?: string;
}

export function SourceBadge({ channel, className }: Props) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "inline-flex min-w-0 items-center gap-1.5 whitespace-nowrap text-xs text-text",
        className,
      )}
      data-source={channel.platform ?? "channel"}
    >
      <PlatformMark platform={channel.platform ?? "channel"} />
      <TruncatedText text={sourceText(t, channel)} />
    </span>
  );
}
