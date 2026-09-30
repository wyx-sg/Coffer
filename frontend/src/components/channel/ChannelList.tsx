// frontend/src/components/channel/ChannelList.tsx
// The left pane of the Channels page: a filter field over the channels, then
// the channels in groups — Needs attention, Connected, Elsewhere (another
// machine runs them) and Off — each with its count. Grouping is by state
// (channelState.ts), so a broken channel always sits at the top.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Skeleton } from "@/components/ui/skeleton";
import type { ResourceOut } from "@/lib/api/resources";
import { searchableName } from "@/lib/resourceTitle";
import { ChannelListRow } from "./ChannelListRow";
import { CHANNEL_GROUPS, channelPlatform, type ChannelView } from "./channelState";
import { platformLabel } from "./PlatformMark";

interface Props {
  channels: readonly ResourceOut[];
  views: Map<string, ChannelView>;
  isLoading: boolean;
  selectedUid: string | null;
  hrefFor: (uid: string) => string;
}

export function ChannelList({ channels, views, isLoading, selectedUid, hrefFor }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return channels;
    return channels.filter((c) =>
      `${platformLabel(channelPlatform(c.config))} ${searchableName(c)}`.toLowerCase().includes(q),
    );
  }, [channels, query]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-3 pb-2.5 pt-3">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("channels.list.filter")}
          ariaLabel={t("channels.list.filter")}
        />
      </div>
      <div className="min-h-0 flex-1 space-y-3.5 overflow-y-auto px-2 pb-3">
        {isLoading ? (
          <div className="space-y-2 px-2.5 py-1" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : visible.length === 0 ? (
          <p className="px-2.5 py-3 text-xs text-text-muted">{t("channels.noMatches")}</p>
        ) : (
          CHANNEL_GROUPS.map((group) => {
            const rows = visible.filter((c) => views.get(c.uid)?.group === group);
            if (rows.length === 0) return null;
            const heading = t(`channels.list.groups.${group}`);
            return (
              <section key={group} aria-label={heading} data-testid={`channel-group-${group}`}>
                <h2 className="flex items-center px-2.5 pb-1 text-2xs font-semibold text-text-muted">
                  {heading}
                  <span className="ml-auto font-book">{rows.length}</span>
                </h2>
                <ul className="flex flex-col gap-px">
                  {rows.map((c) => {
                    const view = views.get(c.uid);
                    if (!view) return null;
                    return (
                      <ChannelListRow
                        key={c.uid}
                        channel={c}
                        view={view}
                        to={hrefFor(c.uid)}
                        current={c.uid === selectedUid}
                      />
                    );
                  })}
                </ul>
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}
