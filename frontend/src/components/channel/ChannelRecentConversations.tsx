// src/components/channel/ChannelRecentConversations.tsx — the latest conversations a channel started, on its Overview.
//
// Under "Conversations from SeaTalk": up to five, newest activity first, each a
// link into that conversation, with the platform's own chat kind and how long
// ago it was active; "All" opens Conversations filtered by this channel. A
// channel that has started none says so in one line.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { Section } from "@/components/Section";
import { TruncatedText } from "@/components/ui/truncated-text";
import { channelConversationsHref } from "@/lib/channels/tabs";
import { useChannelConversations } from "@/lib/hooks/useChannelConversations";

export function ChannelRecentConversations({
  channelUid,
  channelName,
}: {
  channelUid: string;
  channelName: string;
}) {
  const { t, i18n } = useTranslation();
  const recent = useChannelConversations(channelUid);
  const rows = recent.data ?? [];
  return (
    <Section
      title={t("channels.overview.conversations", { name: channelName })}
      labelled
      actions={
        <Link
          to={channelConversationsHref(channelUid)}
          className="inline-flex items-center gap-1 text-xs font-label text-accent-text hover:underline"
          data-testid="channel-conversations-link"
        >
          {t("channels.overview.allConversations")}
          <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      }
    >
      {rows.length === 0 ? (
        <p className="text-sm text-text-muted">
          {recent.isPending ? t("common.loading") : t("channels.overview.noConversations")}
        </p>
      ) : (
        <ul className="flex flex-col" data-testid="channel-recent-conversations">
          {rows.map((c) => (
            <li key={c.id} className="border-t border-border-subtle first:border-t-0">
              <Link
                to={`/conversations/${encodeURIComponent(c.id)}`}
                className="flex min-h-[40px] items-center gap-3 rounded-md px-1 py-1.5 hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
              >
                <span className="flex min-w-0 flex-1 flex-col">
                  <TruncatedText
                    text={c.title || t("palette.untitled")}
                    className="text-sm font-label text-text"
                  />
                  {c.preview ? (
                    <TruncatedText text={c.preview} className="text-xs text-text-muted" />
                  ) : null}
                </span>
                <time
                  dateTime={c.updated_at}
                  className="shrink-0 text-2xs tabular-nums text-text-subtle"
                >
                  {formatRelativeTime(c.updated_at, i18n.language)}
                </time>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
