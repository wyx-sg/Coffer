// src/components/overview/HealthTiles.tsx — the Overview's Health grid: one tile per area that has a backend and is switched on.
//
// Each tile reads its own list hook for its number and the shared attention
// list for its status word, so it loads and fails on its own. An area whose
// feature is off (or not known yet) has no tile; custom tools and CLIs have
// no backend yet and so no tile at all — hidden, not faked.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { UseQueryResult } from "@tanstack/react-query";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { NAV_ENTRIES } from "@/lib/navigation";
import { useActivityInvocations } from "@/lib/hooks/useActivityInvocations";
import { useAgents } from "@/lib/hooks/useAgents";
import { useAttention, type AttentionItem } from "@/lib/hooks/useAttention";
import { useChannels } from "@/lib/hooks/useChannels";
import { useFeatureEnabled, type FeatureKey } from "@/lib/hooks/useFeatures";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useProviders } from "@/lib/hooks/useProviders";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";
import { useSyncStatus } from "@/lib/hooks/useSync";
import {
  AREAS,
  areaProblems,
  areaStatus,
  deliveredAgentCount,
  uidsWithProblems,
  type Area,
} from "@/lib/overview/health";
import { HealthTile, type TileContent } from "./HealthTile";

const DAY_MS = 24 * 60 * 60 * 1000;

interface AreaProps {
  area: Area;
  /** The attention items, or undefined while that list has not answered. */
  items: readonly AttentionItem[] | undefined;
}

type TFn = ReturnType<typeof useTranslation>["t"];

/** The tile's status word from the attention items of its kinds; none while unknown or empty. */
function statusWord(
  t: TFn,
  area: Area,
  items: AreaProps["items"],
  hasObjects: boolean,
): TileContent["status"] {
  if (!items || !hasObjects) return null;
  const status = areaStatus(areaProblems(items, area.kinds));
  if (status.tone === "err") {
    return { tone: "err", text: t("overview.health.failing", { count: status.count }) };
  }
  if (status.tone === "warn") {
    return { tone: "warn", text: t(`overview.health.${area.id}.warn`, { count: status.count }) };
  }
  return { tone: "ok", text: t(`overview.health.${area.id}.ok`) };
}

/** Render one tile over one list query: loading, failed, or its content. */
function AreaTile<T>({
  area,
  query,
  content,
}: {
  area: Area;
  query: UseQueryResult<T>;
  content: (data: T) => TileContent;
}) {
  const { t } = useTranslation();
  const entry = NAV_ENTRIES.find((e) => e.to === area.to);
  if (!entry) return null;
  const label = t(entry.labelKey);
  const state = query.isPending
    ? ({ kind: "loading" } as const)
    : query.isError
      ? ({ kind: "error", error: query.error, retry: () => void query.refetch() } as const)
      : ({ kind: "ready", content: content(query.data as T) } as const);
  return <HealthTile to={area.to} label={label} icon={entry.icon} state={state} />;
}

function AgentsTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useAgents()}
      content={(agents) => {
        const troubled = items ? uidsWithProblems(items, "agent") : null;
        return {
          status: statusWord(t, area, items, agents.length > 0),
          value: troubled ? agents.length - troubled.size : agents.length,
          unit: troubled
            ? t("overview.health.agents.unit", { total: agents.length })
            : t("overview.health.agents.unitRegistered", { count: agents.length }),
          summary:
            agents.length > 0 ? (
              <AgentBadgeGroup
                agents={agents.map((a) => ({
                  type: a.type,
                  name: a.display_name,
                  state: troubled?.has(a.uid) ? "not-connected" : undefined,
                }))}
              />
            ) : null,
        };
      }}
    />
  );
}

/** Up to three names, then "+N". */
function names(list: readonly { name: string; title?: string | null }[]): string {
  const shown = list.slice(0, 3).map((x) => x.title || x.name);
  const rest = list.length - shown.length;
  return rest > 0 ? `${shown.join(", ")} +${rest}` : shown.join(", ");
}

function ProvidersTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useProviders()}
      content={(providers) => ({
        status: statusWord(t, area, items, providers.length > 0),
        value: providers.length,
        unit: t("overview.health.providers.unit", { count: providers.length }),
        summary: providers.length > 0 ? names(providers) : t("overview.health.providers.none"),
      })}
    />
  );
}

function ChannelsTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useChannels()}
      content={(channels) => ({
        status: statusWord(t, area, items, channels.length > 0),
        value: channels.length,
        unit: t("overview.health.channels.unit", { count: channels.length }),
        summary: channels.length > 0 ? names(channels) : t("overview.health.channels.none"),
      })}
    />
  );
}

function McpServersTile({ area, items }: AreaProps) {
  const { t, i18n } = useTranslation();
  // Fixed at mount, so the two counts share one window and one cache key.
  const [since] = useState(() => new Date(Date.now() - DAY_MS).toISOString());
  const calls = useActivityInvocations({ limit: 1, since });
  const failed = useActivityInvocations({ limit: 1, since, status: "error" });
  const callTotal = calls.data?.total;
  const errorTotal = failed.data?.total;
  const fmt = (n: number) => n.toLocaleString(i18n.language);
  return (
    <AreaTile
      area={area}
      query={useResources("mcp_server")}
      content={(servers) => ({
        status: statusWord(t, area, items, servers.length > 0),
        value: servers.length,
        unit: t("overview.health.mcpServers.unit", { count: servers.length }),
        summary:
          typeof callTotal === "number" && typeof errorTotal === "number"
            ? t("overview.health.mcpServers.calls", {
                calls: fmt(callTotal),
                errors: fmt(errorTotal),
              })
            : null,
      })}
    />
  );
}

function SkillsTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useSkills()}
      content={(skills) => {
        const reached = deliveredAgentCount(skills);
        return {
          status: statusWord(t, area, items, skills.length > 0),
          value: skills.length,
          unit: t("overview.health.skills.unit", { count: skills.length }),
          summary:
            skills.length === 0
              ? null
              : reached > 0
                ? t("overview.health.skills.delivered", { count: reached })
                : t("overview.health.skills.notDelivered"),
        };
      }}
    />
  );
}

function KnowledgeTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useKnowledgeCollections()}
      content={(collections) => {
        const docs = collections.reduce((n, c) => n + c.document_count, 0);
        return {
          status: statusWord(t, area, items, collections.length > 0),
          value: docs,
          unit: t("overview.health.knowledge.unit", { count: docs }),
          summary: t("overview.health.knowledge.collections", { count: collections.length }),
        };
      }}
    />
  );
}

function MemoryTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useMemoryPartitions()}
      content={(partitions) => {
        const notes = partitions.reduce((n, p) => n + p.note_count, 0);
        return {
          status: statusWord(t, area, items, partitions.length > 0),
          value: partitions.length,
          unit: t("overview.health.memory.unit", { count: partitions.length }),
          summary: t("overview.health.memory.notes", { count: notes }),
        };
      }}
    />
  );
}

function SyncTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <AreaTile
      area={area}
      query={useSyncStatus()}
      content={(sync) => ({
        status: statusWord(t, area, items, sync.configured),
        value: sync.configured
          ? t(`overview.health.sync.round.${sync.last_run?.status ?? "none"}`, {
              defaultValue: sync.last_run?.status ?? "",
            })
          : t("overview.health.sync.notSetUp"),
        summary: sync.remote?.url ?? t("overview.health.sync.noRemote"),
      })}
    />
  );
}

const TILES: Record<Area["id"], (props: AreaProps) => JSX.Element> = {
  agents: AgentsTile,
  providers: ProvidersTile,
  channels: ChannelsTile,
  mcpServers: McpServersTile,
  skills: SkillsTile,
  knowledge: KnowledgeTile,
  memory: MemoryTile,
  sync: SyncTile,
};

export function HealthTiles() {
  const { t } = useTranslation();
  const attention = useAttention();
  const features: Record<FeatureKey, boolean | undefined> = {
    knowledge: useFeatureEnabled("knowledge"),
    memory: useFeatureEnabled("memory"),
    vault_sync: useFeatureEnabled("vault_sync"),
  };
  const shown = AREAS.filter((a) => !a.feature || features[a.feature] === true);
  return (
    <section aria-labelledby="overview-health" className="space-y-3">
      <h2 id="overview-health" className="text-sm font-semibold">
        {t("overview.health.title")}
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {shown.map((area) => {
          const Tile = TILES[area.id];
          return <Tile key={area.id} area={area} items={attention.data?.items} />;
        })}
      </div>
    </section>
  );
}
