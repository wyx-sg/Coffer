// frontend/src/pages/KnowledgePage.tsx — the one Knowledge surface.
// It lists collections: the top-level folders under `~/.coffer/knowledge/`.
// Every one of them exists because somebody made it — nothing auto-provisions
// a collection, so an empty list means the vault is genuinely empty rather
// than merely untouched (spec knowledge FR-010).
//
// Loads from the DEDICATED `/knowledge/collections` endpoint rather than the
// generic `/resources` list: only the former carries the file counts and the
// README descriptions, both of which are read off disk.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Library, Plus } from "lucide-react";

import { KnowledgeCreateDialog } from "@/components/knowledge/KnowledgeCreateDialog";
import { KnowledgeWelcomePanel } from "@/components/knowledge/KnowledgeWelcomePanel";
import { KnowledgeTable } from "@/components/knowledge/KnowledgeTable";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useKnowledgeCollections } from "@/kinds/knowledge/useKnowledge";
import { translateApiError } from "@/lib/api/errors";

export function KnowledgePage() {
  const { t } = useTranslation();
  const { data, isPending, error, refetch } = useKnowledgeCollections();
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

      <KnowledgeCreateDialog
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
