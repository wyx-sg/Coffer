// src/components/chat/ConversationsFilterBar.tsx — the Conversations list's
// filters, all in the URL (lib/conversations/filters): source (every source,
// Coffer, SeaTalk, Telegram — or the one channel a channel's link narrowed it
// to, shown as a chip that clears back to every source), agent, and the
// archived view.
import { useTranslation } from "react-i18next";
import { Archive, X } from "lucide-react";

import { SkillSegmented } from "@/components/skills/SkillSegmented";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import type { ConversationFilters, SourceFilter } from "@/lib/conversations/filters";

const ALL_AGENTS = "__all__";

interface Props {
  filters: ConversationFilters;
  onChange: (next: ConversationFilters) => void;
  agents: AgentProviderInfo[];
  /** The narrowed-to channel's label, when `filters.channel` is set. */
  channelLabel: string | null;
}

export function ConversationsFilterBar({ filters, onChange, agents, channelLabel }: Props) {
  const { t } = useTranslation();
  const sources: { value: SourceFilter; label: string }[] = [
    { value: "all", label: t("conversations.filters.allSources") },
    { value: "coffer", label: t("conversations.source.coffer") },
    { value: "seatalk", label: "SeaTalk" },
    { value: "telegram", label: "Telegram" },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      {filters.channel ? (
        <span className="inline-flex h-control-sm items-center gap-1 rounded-md border border-border bg-surface-raised pl-2 text-xs">
          {t("conversations.filters.channel", { channel: channelLabel ?? filters.channel })}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("conversations.filters.clearChannel")}
            onClick={() => onChange({ ...filters, channel: null, source: "all" })}
          >
            <X aria-hidden />
          </Button>
        </span>
      ) : (
        <SkillSegmented
          label={t("conversations.filters.source")}
          value={filters.source}
          options={sources}
          onChange={(source) => onChange({ ...filters, source })}
        />
      )}
      <Select
        value={filters.agent ?? ALL_AGENTS}
        onValueChange={(v) => onChange({ ...filters, agent: v === ALL_AGENTS ? null : v })}
      >
        <SelectTrigger
          className="h-control-sm w-40 text-xs"
          aria-label={t("conversations.filters.agent")}
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_AGENTS}>{t("conversations.filters.allAgents")}</SelectItem>
          {agents.map((a) => (
            <SelectItem key={a.agent_key} value={a.agent_key}>
              {a.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto"
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
