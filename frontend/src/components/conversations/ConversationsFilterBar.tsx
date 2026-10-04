// src/components/chat/ConversationsFilterBar.tsx — the Conversations list's
// filter row, all in the URL (lib/conversations/filters): the Active / Archived
// switch, the search over titles and messages ("/" focuses it), a Source pill
// (Coffer and each channel, several at once), an Agent pill, and Clear filters
// once anything narrows the list. It shows no result count.
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import { FilterPill, type FilterOption } from "@/components/filters";
import { Segmented } from "@/components/ui/segmented";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import {
  clearFilters,
  COFFER_SOURCE,
  isFiltered,
  type ConversationFilters,
} from "@/lib/conversations/filters";

/** @ui-only A channel as the Source pill lists it. */
export interface SourceChannel {
  uid: string;
  /** "SeaTalk · Team bot". */
  heading: string;
  platform: string;
}

interface Props {
  filters: ConversationFilters;
  onChange: (next: ConversationFilters) => void;
  agents: AgentProviderInfo[];
  channels: SourceChannel[];
  /** The list below is empty and says "Clear filters" itself. */
  clearInList?: boolean;
}

export function ConversationsFilterBar({
  filters,
  onChange,
  agents,
  channels,
  clearInList = false,
}: Props) {
  const { t } = useTranslation();
  const set = (patch: Partial<ConversationFilters>) => onChange({ ...filters, ...patch });

  const sourceOptions: FilterOption[] = [
    { value: COFFER_SOURCE, label: t("conversations.source.coffer") },
    ...channels.map((ch) => ({ value: ch.uid, label: ch.heading })),
  ];
  // A source named in the link that no channel matches any more is still listed, so it can be unticked.
  const known = new Set(sourceOptions.map((o) => o.value));
  for (const uid of filters.source) {
    if (!known.has(uid)) sourceOptions.push({ value: uid, label: uid });
  }
  const agentOptions: FilterOption[] = agents.map((a) => ({
    value: a.agent_key,
    label: a.display_name,
  }));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented
        label={t("conversations.filters.view")}
        value={filters.archived ? "archived" : "active"}
        options={[
          { value: "active", label: t("conversations.filters.showActive") },
          { value: "archived", label: t("conversations.filters.showArchived") },
        ]}
        onChange={(v) => set({ archived: v === "archived" })}
      />
      <SearchInput
        value={filters.q}
        onChange={(q) => set({ q })}
        ariaLabel={t("conversations.filters.search")}
        placeholder={t("conversations.filters.search")}
        shortcut="/"
        className="w-60"
      />
      <FilterPill
        label={t("conversations.filters.source")}
        options={sourceOptions}
        value={filters.source}
        onChange={(source) => set({ source })}
      />
      <FilterPill
        label={t("conversations.filters.agent")}
        options={agentOptions}
        value={filters.agent}
        onChange={(agent) => set({ agent })}
      />
      {isFiltered(filters) && !clearInList ? (
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          onClick={() => onChange(clearFilters(filters))}
        >
          {t("conversations.list.clearFilters")}
        </Button>
      ) : null}
    </div>
  );
}
