// frontend/src/components/knowledge/KnowledgeCollectionView.tsx
//
// A collection with no document open: its name and what belongs in it, the
// one status line (Documents · Waiting · Curated), and a danger zone. A just
// created, empty collection says how the first document gets in — Add a
// document, Upload, or dropping Markdown into the folder — and that agents
// already see it and can write to its inbox.
//
// No switch and no reach: every collection is served to every agent (spec
// knowledge "Serve every collection to every agent").
import { useTranslation } from "react-i18next";
import { Library, Plus, Upload } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeDeleteCollection } from "@/components/knowledge/KnowledgeDeleteCollection";
import { KnowledgeNoModelLine } from "@/components/knowledge/KnowledgeNoModelLine";
import { KnowledgeStatsLine } from "@/components/knowledge/KnowledgeStatsLine";
import { EditTitleDialog } from "@/components/resource/EditTitleDialog";
import { Button } from "@/components/ui/button";
import type { CollectionOut } from "@/lib/api/knowledge";

interface Props {
  collection: CollectionOut;
  modelSet: boolean | undefined;
  onAdd: () => void;
  onUpload: () => void;
}

export function KnowledgeCollectionView({ collection, modelSet, onAdd, onUpload }: Props) {
  const { t } = useTranslation();
  const empty = collection.document_count === 0 && collection.pending_count === 0;

  return (
    <div className="min-h-0 space-y-6 overflow-auto pb-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-bold">{collection.title || collection.name}</h2>
          {collection.title ? (
            <span className="font-mono text-xs text-text-subtle">{collection.name}</span>
          ) : null}
          <div className="ml-auto flex items-center gap-2">
            <EditTitleDialog kind="knowledge" resource={collection} />
            <Button variant="outline" size="sm" onClick={onAdd}>
              <Plus aria-hidden /> {t("knowledge.add.here")}
            </Button>
          </div>
        </div>
        {collection.description ? (
          <p className="max-w-prose text-sm text-text-muted">{collection.description}</p>
        ) : null}
        <KnowledgeStatsLine collection={collection} modelSet={modelSet} />
        {modelSet === false ? <KnowledgeNoModelLine /> : null}
      </header>

      {empty ? (
        <EmptyState
          icon={Library}
          title={t("knowledge.collection.emptyTitle", { name: collection.name })}
          description={t("knowledge.collection.emptyBody")}
          action={
            <Button onClick={onAdd}>
              <Plus aria-hidden /> {t("knowledge.add.button")}
            </Button>
          }
          secondaryAction={
            <Button variant="outline" onClick={onUpload}>
              <Upload aria-hidden /> {t("knowledge.upload.button")}
            </Button>
          }
        />
      ) : (
        <p className="text-sm text-text-subtle">{t("knowledge.collection.pickDocument")}</p>
      )}

      <KnowledgeDeleteCollection collection={collection} />
    </div>
  );
}
