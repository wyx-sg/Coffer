// src/components/chat/ConversationsFilterBar.tsx — the Conversations list's
// filter row, all in the URL (lib/conversations/filters): the Active / Archived
// switch, the search over titles and messages ("/" focuses it), a Source pill
// (Coffer and each channel, several at once), an Agent pill, and Clear filters
// once anything narrows the list. It shows no result count.
import { useTranslation } from "react-i18next";

import { ChecklistPill, type CheckItem } from "@/components/activity/ChecklistPill";
import { AgentBadge } from "@/components/agent/AgentBadge";
import { CofferMark } from "@/components/brand/CofferMark";
import { PlatformMark } from "@/components/channel/PlatformMark";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import {
  clearFilters,
  COFFER_SOURCE,
  isFiltered,
  toggled,
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

  const chosen = (values: string[], words: (v: string) => string): string | null =>
    values.length === 0
      ? null
      : values.length === 1
        ? words(values[0])
        : t("conversations.filters.selected", { count: values.length });

  const sourceItems: CheckItem[] = [
    {
      value: COFFER_SOURCE,
      text: t("conversations.source.coffer"),
      checked: filters.source.includes(COFFER_SOURCE),
      label: (
        <span className="flex items-center gap-2">
          <span className="inline-flex h-[18px] w-[22px] shrink-0 items-center justify-center rounded-sm bg-chip">
            <CofferMark size={12} className="text-text-muted" />
          </span>
          {t("conversations.source.coffer")}
        </span>
      ),
    },
    ...channels.map((ch) => ({
      value: ch.uid,
      text: ch.heading,
      checked: filters.source.includes(ch.uid),
      label: (
        <span className="flex items-center gap-2">
          <PlatformMark platform={ch.platform} />
          {ch.heading}
        </span>
      ),
    })),
  ];
  // A source named in the link that no channel matches any more is still shown, so it can be unticked.
  const known = new Set(sourceItems.map((i) => i.value));
  for (const uid of filters.source) {
    if (!known.has(uid)) {
      sourceItems.push({ value: uid, text: uid, checked: true, label: uid });
    }
  }
  const agentItems: CheckItem[] = agents.map((a) => ({
    value: a.agent_key,
    text: a.display_name,
    checked: filters.agent.includes(a.agent_key),
    label: (
      <AgentBadge type={a.agent_key} name={a.display_name} size="sm" showName tooltip={false} />
    ),
  }));

  const summary = (values: string[]) =>
    values.length > 0 ? t("conversations.filters.selected", { count: values.length }) : null;

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
      <ChecklistPill
        label={t("conversations.filters.source")}
        valueLabel={chosen(
          filters.source,
          (v) => sourceItems.find((i) => i.value === v)?.text ?? v,
        )}
        groups={[{ items: sourceItems }]}
        onToggle={(v) => set({ source: toggled(filters.source, v) })}
        onClear={() => set({ source: [] })}
        summary={summary(filters.source)}
      />
      <ChecklistPill
        label={t("conversations.filters.agent")}
        valueLabel={chosen(filters.agent, (v) => agentItems.find((i) => i.value === v)?.text ?? v)}
        groups={[{ items: agentItems }]}
        onToggle={(v) => set({ agent: toggled(filters.agent, v) })}
        onClear={() => set({ agent: [] })}
        summary={summary(filters.agent)}
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
