// src/components/overview/contextTiles.tsx — the Health tiles for what the vault keeps: Knowledge, Memory and Sync.
//
// Each reads its own list, like the area tiles beside it (areaTiles.tsx), and
// shows when it last changed (Overview board 1.2.09): "4 collections · edited
// today 13:30", "Last synced 14 min ago", "4 min ago · last round".
import { useTranslation } from "react-i18next";

import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { useMemorySyncState } from "@/lib/hooks/useMemory";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { totalMemories } from "@/lib/memory/syncFacts";
import { tileStatus } from "@/lib/overview/health";
import { agoText, editedText, latest } from "@/lib/overview/tileText";
import type { AreaProps } from "./areaTiles";
import { QueryTile } from "./QueryTile";

export function KnowledgeTile({ area, items }: AreaProps) {
  const { t, i18n } = useTranslation();
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
          summary: [
            t("overview.health.knowledge.collections", { count: collections.length }),
            editedText(t, i18n.language, latest(collections.map((c) => c.updated_at))),
          ]
            .filter(Boolean)
            .join(" · "),
        };
      }}
    />
  );
}

export function MemoryTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useMemorySyncState()}
      content={(state) => {
        const count = totalMemories(state);
        const synced = agoText(t, state.last_synced_at || null);
        return {
          status: tileStatus(t, area, items, count > 0),
          value: count,
          unit: t("overview.health.memory.unit", { count }),
          summary: synced ? t("overview.health.memory.lastUpdate", { ago: synced }) : null,
        };
      }}
    />
  );
}

export function SyncTile({ area, items }: AreaProps) {
  const { t } = useTranslation();
  return (
    <QueryTile
      area={area}
      query={useSyncStatus()}
      content={(sync) => {
        const ago = agoText(t, sync.last_round?.finished_at ?? null);
        return {
          status: tileStatus(t, area, items, sync.configured),
          value: !sync.configured
            ? t("overview.health.sync.notSetUp")
            : (ago ?? t("overview.health.sync.noRound")),
          unit: sync.configured && ago ? t("overview.health.sync.lastRound") : undefined,
          summary: sync.configured
            ? t("overview.health.sync.drift", { behind: sync.behind, ahead: sync.ahead })
            : null,
        };
      }}
    />
  );
}
