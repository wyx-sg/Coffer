// src/components/overview/areaTiles.tsx — one Health tile per area: its number from its own list, its word from its attention items.
//
// Each area's tile is its own component reading its own list hook, so a tile
// loads and fails on its own; HealthTiles decides which of them are shown.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { useActivityInvocations } from "@/lib/hooks/useActivityInvocations";
import { useAgents } from "@/lib/hooks/useAgents";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { useChannels } from "@/lib/hooks/useChannels";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useProviders } from "@/lib/hooks/useProviders";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";
import { useSyncStatus } from "@/lib/hooks/useSync";
import {
  deliveredAgentCount,
  tileStatus,
  uidsWithProblems,
  type Area,
} from "@/lib/overview/health";
import { QueryTile } from "./QueryTile";
import { ClisTile, CustomToolsTile, SecretsTile, UsageTile } from "./systemTiles";

const DAY_MS = 24 * 60 * 60 * 1000;

export interface AreaProps {
  area: Area;
  /** The attention items, or undefined while that list has not answered. */
  items: readonly AttentionItem[] | undefined;
}

function AgentsTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useAgents()}
      content={(agents) => {
        const troubled = items ? uidsWithProblems(items, "agent") : null;
        return {
          status: tileStatus(t, area, items, agents.length > 0),
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
    <QueryTile
      area={area}
      query={useProviders()}
      content={(providers) => ({
        status: tileStatus(t, area, items, providers.length > 0),
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
    <QueryTile
      area={area}
      query={useChannels()}
      content={(channels) => ({
        status: tileStatus(t, area, items, channels.length > 0),
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
    <QueryTile
      area={area}
      query={useResources("mcp_server")}
      content={(servers) => ({
        status: tileStatus(t, area, items, servers.length > 0),
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
    <QueryTile
      area={area}
      query={useSkills()}
      content={(skills) => {
        const reached = deliveredAgentCount(skills);
        return {
          status: tileStatus(t, area, items, skills.length > 0),
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
    <QueryTile
      area={area}
      query={useKnowledgeCollections()}
      content={(collections) => {
        const docs = collections.reduce((n, c) => n + c.document_count, 0);
        return {
          status: tileStatus(t, area, items, collections.length > 0),
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
    <QueryTile
      area={area}
      query={useMemoryPartitions()}
      content={(partitions) => {
        const notes = partitions.reduce((n, p) => n + p.note_count, 0);
        return {
          status: tileStatus(t, area, items, partitions.length > 0),
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
    <QueryTile
      area={area}
      query={useSyncStatus()}
      content={(sync) => ({
        status: tileStatus(t, area, items, sync.configured),
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
  customTools: CustomToolsTile,
  clis: ClisTile,
  secrets: SecretsTile,
  usage: UsageTile,
};

/** The tile for one area. */
export function AreaHealthTile({ area, items }: AreaProps) {
  const Tile = TILES[area.id];
  return <Tile area={area} items={items} />;
}
