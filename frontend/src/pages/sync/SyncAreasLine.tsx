// frontend/src/pages/sync/SyncAreasLine.tsx
//
// What the vault holds that syncs, as the one grey line under the status line
// on every Status board (6.4.01): "Syncs 142 knowledge documents · 38 skills ·
// 24 MCP server and tool definitions · secrets not synced". It replaced the
// four count tiles — a glance does not need a strip of boxes. It ends by
// saying linked knowledge folders never sync: they stay on this machine, kept
// by the person's own tools (spec knowledge "Link a folder the person keeps
// themselves").
import { useTranslation } from "react-i18next";

import type { SyncStatus } from "@/lib/api/sync";

export function SyncAreasLine({ areas }: { areas: SyncStatus["areas"] }) {
  const { t } = useTranslation();
  return (
    <span className="text-xs text-text-subtle" data-testid="sync-areas">
      {t("sync.areas.line", {
        documents: t("sync.areas.documents", { count: areas.knowledge_documents }),
        skills: t("sync.areas.skillCount", { count: areas.skills }),
        definitions: t("sync.areas.definitions", { count: areas.resources }),
        secrets: t(areas.secrets_synced ? "sync.areas.synced" : "sync.areas.notSynced"),
        linked: t("sync.areas.linkedNotSynced"),
      })}
    </span>
  );
}
