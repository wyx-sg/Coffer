// frontend/src/pages/MemoryPage.tsx — spec 007-memory surface.
// Mirrors KnowledgeBasesPage/SkillsPage: PageHeader + welcome/loading/error/
// table; the Add-store header action appears only once stores exist — the
// empty state's welcome panel carries the Add call-to-action instead. Creation
// happens in a modal dialog.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { BrainCircuit, Plus } from "lucide-react";

import { MemoryStoreAddDialog } from "@/components/memory/MemoryStoreAddDialog";
import { MemoryWelcomePanel } from "@/components/memory/MemoryWelcomePanel";
import { MemoryStoresTable } from "@/components/memory/MemoryStoresTable";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useResources } from "@/lib/hooks/useResources";

export function MemoryPage() {
  const { t } = useTranslation();
  const { data: items, isPending, error, refetch } = useResources("memory");
  const [showAdd, setShowAdd] = useState(false);
  const hasItems = (items ?? []).length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BrainCircuit}
        title={t("memory.title")}
        subtitle={t("memory.subtitle")}
        actions={
          hasItems ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="mr-1 size-4" /> {t("memory.add")}
            </Button>
          ) : null
        }
      />

      <MemoryStoreAddDialog
        open={showAdd}
        onOpenChange={setShowAdd}
        onCreated={() => void refetch()}
      />

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
        <MemoryWelcomePanel onAdd={() => setShowAdd(true)} />
      ) : (
        <MemoryStoresTable items={items ?? []} />
      )}
    </div>
  );
}
