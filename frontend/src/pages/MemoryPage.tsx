// frontend/src/pages/MemoryPage.tsx — spec 007-memory surface.
// Memory stores are AUTO-PROVISIONED (a global store plus one per project), so
// there is no "New store" action: the page lists what exists. Mirrors
// KnowledgeBasesPage/SkillsPage for the welcome/loading/error/table states.
import { useTranslation } from "react-i18next";
import { BrainCircuit } from "lucide-react";

import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { MemoryStoresTable } from "@/components/memory/MemoryStoresTable";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useResources } from "@/lib/hooks/useResources";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: items, isPending, error } = useResources("memory");
  const hasItems = (items ?? []).length > 0;

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
        <MemoryStoresTable items={items ?? []} />
      )}
    </div>
  );
}
