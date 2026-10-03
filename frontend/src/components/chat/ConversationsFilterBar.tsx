// src/components/chat/ConversationsFilterBar.tsx — the Conversations list's
// filters, all in the URL (lib/conversations/filters): source (every source,
// Coffer, SeaTalk, Telegram), agent, the one channel a channel's link narrowed
// it to (a chip beside the agent filter that clears back to every source), and
// the archived view.
import { useTranslation } from "react-i18next";
import { Archive, X } from "lucide-react";

import { SearchInput } from "@/components/SearchInput";
import { SkillSegmented } from "@/components/skills/SkillSegmented";
import { Button } from "@/components/ui/button";
import { FilterPill } from "@/components/filters";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import type { ConversationFilters, SourceFilter } from "@/lib/conversations/filters";

interface Props {
  filters: ConversationFilters;
  onChange: (next: ConversationFilters) => void;
  agents: AgentProviderInfo[];
  /** The narrowed-to channel's label, when `filters.channel` is set. */
  channelLabel: string | null;
  /** The platform of the channel in `filters.channel`, for the source switch. */
  channelSource?: SourceFilter | null;
  /** The title search's text; the server is asked for it once typing pauses. */
  search: string;
  onSearch: (text: string) => void;
}

export function ConversationsFilterBar({
  filters,
  onChange,
  agents,
  channelLabel,
  channelSource = null,
  search,
  onSearch,
}: Props) {
  const { t } = useTranslation();
  const sources: { value: SourceFilter; label: string }[] = [
    { value: "all", label: t("conversations.filters.allSources") },
    { value: "coffer", label: t("conversations.source.coffer") },
    { value: "seatalk", label: "SeaTalk" },
    { value: "telegram", label: "Telegram" },
  ];

  const sourceValue = filters.channel ? (channelSource ?? "all") : filters.source;

  return (
    <div className={"flex flex-wrap items-center gap-2"}>
      {/* A channel's link narrows further than its platform: the switch keeps
          showing that platform, and picking any source drops the channel. */}
      <SkillSegmented
        label={t("conversations.filters.source")}
        value={sourceValue}
        options={sources}
        onChange={(source) => onChange({ ...filters, source, channel: null })}
      />
      <FilterPill
        mode="single"
        label={t("conversations.filters.agent")}
        options={agents.map((a) => ({ value: a.agent_key, label: a.display_name }))}
        value={filters.agent}
        onChange={(agent) => onChange({ ...filters, agent })}
      />
      {filters.channel ? (
        <span className="inline-flex h-control-sm items-center gap-1 rounded-md bg-accent-soft pl-2 text-xs font-label text-accent-text">
          {t("conversations.filters.channel", { channel: channelLabel ?? filters.channel })}
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-accent-text hover:bg-transparent"
            aria-label={t("conversations.filters.clearChannel")}
            onClick={() => onChange({ ...filters, channel: null, source: "all" })}
          >
            <X aria-hidden />
          </Button>
        </span>
      ) : null}
      <SearchInput
        value={search}
        onChange={onSearch}
        ariaLabel={t("conversations.filters.search")}
        placeholder={t("conversations.filters.search")}
        className="ml-auto w-56"
      />
      <Button
        variant="ghost"
        size="sm"
        aria-pressed={filters.archived}
        onClick={() => onChange({ ...filters, archived: !filters.archived })}
      >
        <Archive aria-hidden />
        {filters.archived
          ? t("conversations.filters.showActive")
          : t("conversations.filters.showArchived")}
      </Button>
    </div>
  );
}
