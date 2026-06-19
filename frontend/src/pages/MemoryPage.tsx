// frontend/src/pages/MemoryPage.tsx — spec 007-memory surface.
// Memory stores are AUTO-PROVISIONED (a global store plus one per project), so
// there is no "New store" action: the page lists what exists. Mirrors
// KnowledgeBasesPage/SkillsPage for the welcome/loading/error/table states.
//
// Loads from the DEDICATED `/memory_stores` endpoint rather than the generic
// `/resources` list: only the former carries the typed `scope`/`project_id`
// the table's scope column needs (the generic row has neither, so every store
// would mislabel as "Unknown").
import { useTranslation } from "react-i18next";
import { BrainCircuit } from "lucide-react";

import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { MemoryStoresTable } from "@/components/memory/MemoryStoresTable";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useMemoryStores } from "@/lib/hooks/useMemoryStores";
import { translateApiError } from "@/lib/api/errors";

export function MemoryPage() {
  const { t } = useTranslation();
  // Shared hook: caches the store ARRAY under ["memory-stores"]. The agent
  // Memory tab reads the same key, so the page must not register a second
  // query there returning a different shape (that collision crashed the tab).
  const { data, isPending, error } = useMemoryStores();
  const items = data ?? [];
  const hasItems = items.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader icon={BrainCircuit} title={t("memory.title")} subtitle={t("memory.subtitle")} />

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("memory.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !hasItems ? (
        <MemoryWelcomePanel />
      ) : (
        <MemoryStoresTable items={items} />
      )}
    </div>
  );
}
