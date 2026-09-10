// frontend/src/pages/KnowledgePage.tsx — the one Knowledge surface.
// `memory` and `knowledge_base` used to be two pages; a scope is a scope
// whether it holds notes an agent wrote or documents someone uploaded, so
// this lists all three kinds of scope in one table. `global` and
// `project-<ULID>` auto-provision; the "New collection" action creates a NAMED
// collection (the only kind a person creates by hand).
//
// Loads from the DEDICATED `/knowledge` endpoint rather than the generic
// `/resources` list: only the former carries the two per-lane counts the table
// needs.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Library, Plus } from "lucide-react";

import { KnowledgeAddDialog } from "@/components/knowledge/KnowledgeAddDialog";
import { KnowledgeWelcomePanel } from "@/components/knowledge/KnowledgeWelcomePanel";
import { KnowledgeTable } from "@/components/knowledge/KnowledgeTable";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useKnowledgeScopes } from "@/lib/hooks/useKnowledgeScopes";
import { translateApiError } from "@/lib/api/errors";

export function KnowledgePage() {
  const { t } = useTranslation();
  // Shared hook: caches the scope ARRAY under ["knowledge-scopes"].
  const { data, isPending, error, refetch } = useKnowledgeScopes();
  const items = data ?? [];
  const hasItems = items.length > 0;
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Library}
        title={t("knowledge.title")}
        subtitle={t("knowledge.subtitle")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {hasItems ? (
              <Button onClick={() => setShowAdd(true)}>
                <Plus className="mr-1 size-4" /> {t("knowledge.add")}
              </Button>
            ) : null}
          </div>
        }
      />

      <KnowledgeAddDialog
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
            <CardTitle className="text-destructive">{t("knowledge.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : !hasItems ? (
        <KnowledgeWelcomePanel onAdd={() => setShowAdd(true)} />
      ) : (
        <KnowledgeTable items={items} />
      )}
    </div>
  );
}
