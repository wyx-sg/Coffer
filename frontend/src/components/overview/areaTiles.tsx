// src/components/overview/areaTiles.tsx — one Health tile per area: its number from its own list, its word from its attention items.
//
// Each area's tile is its own component reading its own list hook, so a tile
// loads and fails on its own; HealthTiles decides which of them are shown.
// The numbers and detail lines follow Overview board 1.2.09 (every tile in its
// normal state): "1 of 2 connected" for Agents and Channels. Knowledge,
// Memory and Sync, which show when they last changed, are in contextTiles.tsx.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentBadgeGroup } from "@/components/agent/AgentBadgeGroup";
import { useActivityInvocations } from "@/lib/hooks/useActivityInvocations";
import { useAgents } from "@/lib/hooks/useAgents";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { useChannels } from "@/lib/hooks/useChannels";
import { useProviders } from "@/lib/hooks/useProviders";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";
import {
  CONNECT_REASONS,
  deliveredAgentCount,
  tileStatus,
  uidsWithProblems,
  type Area,
} from "@/lib/overview/health";
import { joinNames, reconnectingText } from "@/lib/overview/tileText";
import { KnowledgeTile, MemoryTile, SyncTile } from "./contextTiles";
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
        // Only connecting counts: a hook edited by hand is a Needs you row, not a missing connection.
        const troubled = items ? uidsWithProblems(items, "agent", CONNECT_REASONS) : null;
        return {
          status: tileStatus(t, area, items, agents.length > 0),
          value: troubled
            ? t("overview.health.ofTotal", {
                count: agents.length - troubled.size,
                total: agents.length,
              })
            : agents.length,
          unit: troubled
            ? t("overview.health.connected")
            : t("overview.health.agents.unitRegistered", { count: agents.length }),
          summary:
            agents.length > 0 ? (
              <AgentBadgeGroup
                agents={agents.map((a) => ({
                  type: a.type,
                  name: a.display_name,
                }))}
              />
            ) : null,
        };
      }}
    />
  );
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
        summary: providers.length > 0 ? joinNames(providers) : t("overview.health.providers.none"),
      })}
    />
  );
}

function ChannelsTile({ area, items }: AreaProps) {
  const { t, i18n } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useChannels()}
      content={(channels) => {
        const troubled = items ? uidsWithProblems(items, "channel") : null;
        // The oldest reconnecting channel is the one the line names.
        const reconnecting = items
          ?.filter((i) => i.kind === "channel" && i.reason_code === "channel_reconnecting")
          .sort((a, b) => (a.since ?? "").localeCompare(b.since ?? ""))[0];
        return {
          status: tileStatus(t, area, items, channels.length > 0),
          value: troubled
            ? t("overview.health.ofTotal", {
                count: channels.length - troubled.size,
                total: channels.length,
              })
            : channels.length,
          unit: troubled
            ? t("overview.health.connected")
            : t("overview.health.channels.unit", { count: channels.length }),
          summary:
            channels.length === 0
              ? t("overview.health.channels.none")
              : reconnecting
                ? reconnectingText(t, i18n.language, reconnecting.title, reconnecting.since ?? null)
                : joinNames(channels),
        };
      }}
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
