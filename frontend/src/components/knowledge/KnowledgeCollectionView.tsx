// frontend/src/components/knowledge/KnowledgeCollectionView.tsx
//
// A collection with no document open (boards 5.1.13, 5.1.14, 5.1.25). A
// collection has no title: its heading is its folder name, and what belongs
// in it is its description — the opening paragraph of its README, edited in
// place with Edit description. Under it the one status row (Documents ·
// Waiting · Curated) and a danger zone. A just created, empty collection is
// only the empty state: how the first document gets in — Add a document,
// Upload, or dropping Markdown into the folder (Reveal folder) — and that
// agents already see it and can write to its inbox.
//
// No switch and no reach: every collection is served to every agent (spec
// knowledge "Serve every collection to every agent").
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, Book, Pencil, Plus, Upload } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { SectionStack } from "@/components/Section";
import { KnowledgeDeleteCollection } from "@/components/knowledge/KnowledgeDeleteCollection";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { KnowledgeStatsLine } from "@/components/knowledge/KnowledgeStatsLine";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useFsActions } from "@/lib/fsActions";
import { useDescribeCollection } from "@/lib/hooks/useKnowledgeHistory";

interface Props {
  collection: CollectionOut;
  modelSet: boolean | undefined;
  onAdd: () => void;
  onUpload: () => void;
}

export function KnowledgeCollectionView({ collection, modelSet, onAdd, onUpload }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const [editing, setEditing] = useState(false);
  const empty = collection.document_count === 0 && collection.pending_count === 0;

  const revealFolder = () =>
    void reveal(collection.folder_path).catch(() => toast.error(t("fileActions.revealFailed")));

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar
        crumbs={[{ label: collection.name, mono: true }]}
        actions={
          <Button variant="outline" onClick={() => setEditing(true)} disabled={editing}>
            <Pencil aria-hidden /> {t("knowledge.collection.editDescription")}
          </Button>
        }
      />

      {empty && !editing ? (
        <div className="flex min-h-0 flex-1 items-center justify-center p-6">
          <EmptyState
            icon={Book}
            title={t("knowledge.collection.emptyTitle", { name: collection.name })}
            description={t("knowledge.collection.emptyBody")}
            action={
              <>
                <Button onClick={onAdd}>
                  <Plus aria-hidden /> {t("knowledge.add.button")}
                </Button>
                <Button variant="outline" onClick={onUpload}>
                  <Upload aria-hidden /> {t("knowledge.upload.button")}
                </Button>
                {collection.folder_path ? (
                  <Button variant="outline" onClick={revealFolder}>
                    <FolderOpen aria-hidden /> {t("knowledge.collection.revealFolder")}
                  </Button>
                ) : null}
              </>
            }
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto px-10 py-[22px]">
          <SectionStack className="max-w-[680px]">
            <div className="flex flex-col gap-2">
              <h2 className="font-mono text-lg font-medium">{collection.name}</h2>
              {editing ? (
                <DescriptionEditor collection={collection} onDone={() => setEditing(false)} />
              ) : collection.description ? (
                <p className="max-w-[620px] text-[14px] leading-[1.65]">{collection.description}</p>
              ) : (
                <p className="text-sm text-text-subtle">
                  {t("knowledge.collection.noDescription")}
                </p>
              )}
            </div>
            <KnowledgeStatsLine collection={collection} modelSet={modelSet} />
            <KnowledgeDeleteCollection collection={collection} />
          </SectionStack>
        </div>
      )}
    </div>
  );
}

function DescriptionEditor({
  collection,
  onDone,
}: {
  collection: CollectionOut;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const describe = useDescribeCollection(collection.uid);
  const [value, setValue] = useState(collection.description);
  const text = value.trim();
  const save = () => describe.mutate(text, { onSuccess: onDone });

  return (
    <div className="flex max-w-[620px] flex-col gap-2">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label={t("knowledge.collection.descriptionLabel")}
        autoFocus
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && text) {
            e.preventDefault();
            save();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onDone();
          }
        }}
      />
      <p className="text-xs text-text-subtle">{t("knowledge.collection.descriptionHint")}</p>
      {describe.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, describe.error)}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button onClick={save} disabled={!text || describe.isPending} loading={describe.isPending}>
          {t("common.save")}
        </Button>
        <Button variant="outline" onClick={onDone} disabled={describe.isPending}>
          {t("common.cancel")}
        </Button>
      </div>
    </div>
  );
}
