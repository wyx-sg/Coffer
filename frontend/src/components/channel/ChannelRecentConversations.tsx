// src/components/channel/ChannelRecentConversations.tsx — the latest conversations a channel started, on its Overview.
//
// Under "Conversations from SeaTalk": up to five, newest activity first, each a
// link into that conversation, with the platform's own chat kind and how long
// ago it was active; "Open Conversations" opens Conversations filtered by this channel. A
// channel that has started none says so in one line.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Button } from "@/components/ui/button";
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
    <SettingsSection
      title={t("channels.overview.conversations", { name: channelName })}
      headingLevel={3}
      action={
        <Button asChild size="sm" variant="ghost">
          <Link to={channelConversationsHref(channelUid)} data-testid="channel-conversations-link">
            {t("channels.overview.allConversations")}
          </Link>
        </Button>
      }
    >
      {rows.length === 0 ? (
        <p className="rounded-lg border border-border-subtle px-3 py-3 text-sm text-text-muted">
          {recent.isPending ? t("common.loading") : t("channels.overview.noConversations")}
        </p>
      ) : (
        <ul
          className="flex flex-col rounded-lg border border-border-subtle"
          data-testid="channel-recent-conversations"
        >
          {rows.map((c) => (
            <li key={c.id} className="border-t border-border-subtle first:border-t-0">
              <Link
                to={`/conversations/${encodeURIComponent(c.id)}`}
                className="flex min-h-[40px] items-center gap-3 rounded-lg px-3 py-1.5 hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
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
    </SettingsSection>
  );
}
