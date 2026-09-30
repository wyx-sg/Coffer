// src/components/palette/paletteSources.ts — what the palette lists: the pages, and one existing list hook per object kind.
//
// Each kind's hook runs in a small component mounted only while the palette is
// open, and reports its state up, so one failing list leaves the others
// working and nothing is fetched while the palette is closed.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useAgents } from "@/lib/hooks/useAgents";
import { useChannels } from "@/lib/hooks/useChannels";
import { useCustomToolGroups } from "@/lib/hooks/useCustomTools";
import { useClis } from "@/lib/hooks/useClis";
import { isFeatureOn, type FeatureKey } from "@/lib/hooks/useFeatures";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useProviders } from "@/lib/hooks/useProviders";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";
import { isCustomToolGroup } from "@/lib/customTools/groups";
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

// One hook per kind, each the list hook that kind's own page reads.
const useAgentObjects = () => kindState(useAgents());
// A custom-tool group is an `mcp_server` too; it is listed as a custom tool.
const useMcpServerObjects = (): KindState => {
  const q = useResources("mcp_server");
  const items = useMemo(() => q.data?.filter((r) => !isCustomToolGroup(r)), [q.data]);
  return kindState({ status: q.status, data: items });
};
const useCustomToolObjects = () => kindState(useCustomToolGroups());
const useSkillObjects = () => kindState(useSkills());
const useProviderObjects = () => kindState(useProviders());
const useChannelObjects = () => kindState(useChannels());
const useKnowledgeObjects = () => kindState(useKnowledgeCollections());
const useMemoryObjects = () => kindState(useMemoryPartitions());
// A command has no uid: it is its own identity, so it stands in as both.
const useCliObjects = (): KindState => {
  const q = useClis();
  const items = useMemo(
    () => q.data?.items.map((cli) => ({ uid: cli.command, name: cli.command, title: cli.title })),
    [q.data],
  );
  return kindState({ status: q.status, data: items });
};

export const KIND_LIST_HOOKS: Record<ObjectKind, () => KindState> = {
  agent: useAgentObjects,
  mcpServer: useMcpServerObjects,
  skill: useSkillObjects,
  provider: useProviderObjects,
  channel: useChannelObjects,
  knowledge: useKnowledgeObjects,
  memory: useMemoryObjects,
  customTool: useCustomToolObjects,
  cli: useCliObjects,
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
  "customTool",
  "cli",
];

/** Every sidebar entry of a switched-on feature and every Settings tab, by the
 *  names the sidebar and the tabs use. */
export function usePageItems(features: Record<FeatureKey, boolean> | null): PaletteItem[] {
  const { t } = useTranslation();
  return useMemo<PaletteItem[]>(() => {
    const entries: PaletteItem[] = NAV_ENTRIES.filter((entry) =>
      isFeatureOn(features, entry.feature),
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
