// frontend/src/pages/sync/SyncAreaTiles.tsx
//
// What the vault holds that syncs, in the same four counts on every status
// board: knowledge documents, skills, MCP servers & tools definitions, and
// whether encrypted secrets travel with the rest. One bordered strip, four
// cells — a glance, not a table.
import type { LucideIcon } from "lucide-react";
import { BookOpen, Lock, Server, Sparkle } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { SyncStatus } from "@/lib/api/sync";

function Tile({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2.5 px-3.5 py-3 [&+&]:border-l [&+&]:border-border-subtle">
      <Icon className="size-4 shrink-0 text-text-muted" aria-hidden />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-xs font-label text-text">{label}</span>
        <span className="truncate text-xs text-text-muted">{value}</span>
      </div>
    </div>
  );
}

export function SyncAreaTiles({ areas }: { areas: SyncStatus["areas"] }) {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-wrap rounded-xl border border-border bg-surface-raised"
      data-testid="sync-areas"
    >
      <Tile
        icon={BookOpen}
        label={t("sync.areas.knowledge")}
        value={t("sync.areas.documents", { count: areas.knowledge_documents })}
      />
      <Tile
        icon={Sparkle}
        label={t("sync.areas.skills")}
        value={t("sync.areas.skillCount", { count: areas.skills })}
      />
      <Tile
        icon={Server}
        label={t("sync.areas.resources")}
        value={t("sync.areas.definitions", { count: areas.resources })}
      />
      <Tile
        icon={Lock}
        label={t("sync.areas.secrets")}
        value={t(areas.secrets_synced ? "sync.areas.synced" : "sync.areas.notSynced")}
      />
    </div>
  );
}
