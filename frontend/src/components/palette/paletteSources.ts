// src/components/palette/paletteSources.ts — what the palette lists: the pages, and one existing list hook per object kind.
//
// Each kind's hook runs in a small component mounted only while the palette is
// open, and reports its state up, so one failing list leaves the others
// working and nothing is fetched while the palette is closed. A status word is
// taken only from what the list row already carries; the palette asks for
// nothing more.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useAgents } from "@/lib/hooks/useAgents";
import { useChannels } from "@/lib/hooks/useChannels";
import { useConversations } from "@/lib/hooks/useConversations";
import { useCustomToolGroups } from "@/lib/hooks/useCustomTools";
import { useClis } from "@/lib/hooks/useClis";
import { isFeatureOn, type FeatureKey } from "@/lib/hooks/useFeatures";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMemoryPartitions } from "@/lib/hooks/useMemory";
import { useProviders } from "@/lib/hooks/useProviders";
import { useResources } from "@/lib/hooks/useResources";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { useSkills } from "@/lib/hooks/useSkills";
import { isCustomToolGroup } from "@/lib/customTools/groups";
import { NAV_ENTRIES, SETTINGS_TABS } from "@/lib/navigation";
import type { ObjectKind, PaletteItem, PaletteObject, PaletteStatus } from "./paletteItems";

/** What one kind's list says right now. */
export interface KindState {
  status: "pending" | "error" | "success";
  items: readonly PaletteObject[];
}

const NO_ITEMS: readonly PaletteObject[] = [];
const OFF: PaletteStatus = { key: "off", tone: "muted" };

function kindState(q: { status: KindState["status"]; data?: readonly PaletteObject[] }): KindState {
  return { status: q.status, items: q.data ?? NO_ITEMS };
}

/** A list's rows as palette objects, mapped once per answer. */
function useMapped<T>(
  q: { status: KindState["status"]; data?: readonly T[] },
  map: (row: T) => PaletteObject,
): KindState {
  const items = useMemo(() => q.data?.map(map), [q.data, map]);
  return kindState({ status: q.status, data: items });
}

type Switchable = PaletteObject & { enabled: boolean };
const offWhenDisabled = (row: Switchable): PaletteObject => ({
  ...row,
  status: row.enabled ? undefined : OFF,
});

const CUSTOM_TOOL_STATUS: Partial<Record<string, PaletteStatus>> = {
  failing: { key: "failing", tone: "error" },
  attention: { key: "attention", tone: "warn" },
  off: OFF,
};
const CLI_STATUS: Partial<Record<string, PaletteStatus>> = {
  missing: { key: "notFound", tone: "warn" },
  outdated: { key: "outdated", tone: "warn" },
  logged_out: { key: "loggedOut", tone: "warn" },
};

// One hook per kind, each the list hook that kind's own page reads.
const useAgentObjects = () => kindState(useAgents());
// A custom-tool group is an `mcp_server` too; it is listed as a custom tool.
const useMcpServerObjects = (): KindState => {
  const q = useResources("mcp_server");
  const items = useMemo(
    () => q.data?.filter((r) => !isCustomToolGroup(r)).map(offWhenDisabled),
    [q.data],
  );
  return kindState({ status: q.status, data: items });
};
const mapCustomTool = (g: PaletteObject & { health: string }) => ({
  ...g,
  status: CUSTOM_TOOL_STATUS[g.health],
});
const useCustomToolObjects = () => useMapped(useCustomToolGroups(), mapCustomTool);
const useSkillObjects = () => useMapped(useSkills(), offWhenDisabled);
const useProviderObjects = () => useMapped(useProviders(), offWhenDisabled);
const useChannelObjects = () => useMapped(useChannels(), offWhenDisabled);
const useKnowledgeObjects = () => kindState(useKnowledgeCollections());
const useMemoryObjects = () => kindState(useMemoryPartitions());
// A command has no uid: it is its own identity, so it stands in as both.
const useCliObjects = (): KindState => {
  const q = useClis();
  const items = useMemo(
    () =>
      q.data?.items.map((cli) => ({
        uid: cli.command,
        name: cli.command,
        title: cli.title,
        status: CLI_STATUS[cli.status],
      })),
    [q.data],
  );
  return kindState({ status: q.status, data: items });
};
// A conversation is named by its title; one without a title by its first line.
const useConversationObjects = (): KindState => {
  const { t } = useTranslation();
  const q = useConversations();
  const items = useMemo(
    () =>
      q.data?.map((c) => ({
        uid: c.id,
        name: c.title.trim() || c.preview?.trim() || t("palette.untitled"),
        status: c.running ? ({ key: "running", tone: "muted" } as const) : undefined,
      })),
    [q.data, t],
  );
  return kindState({ status: q.status, data: items });
};
// A secret is its ref; the listing carries no value, only who uses it.
const useSecretObjects = (): KindState => {
  const { t } = useTranslation();
  const q = useSecrets();
  const items = useMemo(
    () =>
      q.data?.refs.map((s) => ({
        uid: s.ref,
        name: s.ref,
        status: s.present ? undefined : ({ key: "missing", tone: "warn" } as const),
        note:
          s.cited_by.length > 0
            ? t("palette.usedBy", {
                name: s.cited_by[0].name,
                count: s.cited_by.length,
                more: s.cited_by.length - 1,
              })
            : undefined,
      })),
    [q.data, t],
  );
  return kindState({ status: q.status, data: items });
};

export const KIND_LIST_HOOKS: Record<ObjectKind, () => KindState> = {
  agent: useAgentObjects,
  provider: useProviderObjects,
  conversation: useConversationObjects,
  channel: useChannelObjects,
  mcpServer: useMcpServerObjects,
  customTool: useCustomToolObjects,
  skill: useSkillObjects,
  cli: useCliObjects,
  knowledge: useKnowledgeObjects,
  memory: useMemoryObjects,
  secret: useSecretObjects,
};

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
        kind: "page",
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
        kind: "settings",
        label,
        haystack: [label, tabLabel],
        target: { type: "settings", tab: tab.id },
      };
    });
    return [...entries, ...tabs];
  }, [features, t]);
}
