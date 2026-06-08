// frontend/src/pages/KnowledgeBasesPage.tsx — spec 006-knowledge-base surface.
// Mirrors SkillsPage: PageHeader + welcome/loading/error/table; the Add-KB
// header action appears only once KBs exist — the empty state's welcome panel
// carries the Add call-to-action instead. Creation happens in a modal dialog.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Library, Plus } from "lucide-react";

import { KnowledgeBaseAddDialog } from "@/components/knowledge_base/KnowledgeBaseAddDialog";
import { KnowledgeBaseWelcomePanel } from "@/components/knowledge_base/KnowledgeBaseWelcomePanel";
import { KnowledgeBasesTable } from "@/components/knowledge_base/KnowledgeBasesTable";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useResources } from "@/lib/hooks/useResources";

export function KnowledgeBasesPage() {
  const { t } = useTranslation();
  const { data: items, isPending, error, refetch } = useResources("knowledge_base");
  const [showAdd, setShowAdd] = useState(false);
  const hasItems = (items ?? []).length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Library}
        title={t("knowledgeBases.title")}
        subtitle={t("knowledgeBases.subtitle")}
        actions={
          hasItems ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="mr-1 size-4" /> {t("knowledgeBases.add")}
            </Button>
          ) : null
        }
      />

      <KnowledgeBaseAddDialog
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
            <CardTitle className="text-destructive">{t("knowledgeBases.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !hasItems ? (
        <KnowledgeBaseWelcomePanel onAdd={() => setShowAdd(true)} />
      ) : (
        <KnowledgeBasesTable items={items ?? []} />
      )}
    </div>
  );
}
