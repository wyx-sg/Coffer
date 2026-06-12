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
import { useQuery } from "@tanstack/react-query";
import { BrainCircuit } from "lucide-react";

import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { MemoryStoresTable } from "@/components/memory/MemoryStoresTable";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listMemoryStores } from "@/kinds/memory/api";
import { translateApiError } from "@/lib/api/errors";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data, isPending, error } = useQuery({
    queryKey: ["memory-stores"],
    queryFn: listMemoryStores,
  });
  const items = data?.memory_stores ?? [];
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
