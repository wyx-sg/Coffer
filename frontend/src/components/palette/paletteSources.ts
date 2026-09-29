// src/components/palette/paletteSources.ts — what the palette lists: the pages, and one existing list hook per object kind.
//
// Each kind's hook runs in a small component mounted only while the palette is
// open, and reports its state up, so one failing list leaves the others
// working and nothing is fetched while the palette is closed.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useAgents } from "@/lib/hooks/useAgents";
import { useChannels } from "@/lib/hooks/useChannels";
import { useFeatureEnabled, type FeatureKey } from "@/lib/hooks/useFeatures";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useProviders } from "@/lib/hooks/useProviders";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";
import { NAV_ENTRIES, SETTINGS_TABS } from "@/lib/navigation";
import type { ObjectKind, PaletteItem, PaletteObject } from "./paletteItems";

/** What one kind's list says right now. */
export interface KindState {
  status: "pending" | "error" | "success";
  items: readonly PaletteObject[];
}

const NO_ITEMS: readonly PaletteObject[] = [];

function kindState(q: { status: KindState["status"]; data?: readonly PaletteObject[] }): KindState {
  return { status: q.status, items: q.data ?? NO_ITEMS };
}

// One hook per kind, each the list hook that kind's own page reads. Custom
// tools and CLIs have no list route yet; they join when their pages land.
const useAgentObjects = () => kindState(useAgents());
const useMcpServerObjects = () => kindState(useResources("mcp_server"));
const useSkillObjects = () => kindState(useSkills());
const useProviderObjects = () => kindState(useProviders());
const useChannelObjects = () => kindState(useChannels());
const useKnowledgeObjects = () => kindState(useKnowledgeCollections());
const useMemoryObjects = () => kindState(useMemoryPartitions());

export const KIND_LIST_HOOKS: Record<ObjectKind, () => KindState> = {
  agent: useAgentObjects,
  mcpServer: useMcpServerObjects,
  skill: useSkillObjects,
  provider: useProviderObjects,
  channel: useChannelObjects,
  knowledge: useKnowledgeObjects,
  memory: useMemoryObjects,
};

/** Kinds in the order their objects are listed. */
export const OBJECT_KINDS: readonly ObjectKind[] = [
  "agent",
  "mcpServer",
  "skill",
  "provider",
  "channel",
  "knowledge",
  "memory",
];

/** The experimental feature a kind belongs to; while it is not switched on the
 *  kind is not fetched and not listed. */
export const KIND_FEATURE: Partial<Record<ObjectKind, FeatureKey>> = {
  knowledge: "knowledge",
  memory: "memory",
};

export function useFeatureMap(): Record<FeatureKey, boolean> {
  const knowledge = useFeatureEnabled("knowledge") === true;
  const memory = useFeatureEnabled("memory") === true;
  const vaultSync = useFeatureEnabled("vault_sync") === true;
  return useMemo(
    () => ({ knowledge, memory, vault_sync: vaultSync }),
    [knowledge, memory, vaultSync],
  );
}

/** Every sidebar entry of a switched-on feature and every Settings tab, by the
 *  names the sidebar and the tabs use. */
export function usePageItems(features: Record<FeatureKey, boolean>): PaletteItem[] {
  const { t } = useTranslation();
  return useMemo<PaletteItem[]>(() => {
    const entries: PaletteItem[] = NAV_ENTRIES.filter(
      (entry) => entry.feature === undefined || features[entry.feature],
    ).map((entry) => {
      const label = t(entry.labelKey);
      return {
        id: `page${entry.to.replace(/\//g, "-")}`,
        group: "pages",
        label,
        haystack: [label],
        target: { type: "route", to: entry.to },
      };
    });
    const tabs: PaletteItem[] = SETTINGS_TABS.map((tab) => {
      const tabLabel = t(tab.labelKey);
      const label = t("palette.settingsTab", { tab: tabLabel });
      return {
        id: `settings-${tab.id}`,
        group: "pages",
        label,
        haystack: [label, tabLabel],
        target: { type: "settings", tab: tab.id },
      };
    });
    return [...entries, ...tabs];
  }, [features, t]);
}
