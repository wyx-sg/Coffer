// frontend/src/kinds/knowledge/KnowledgeDetailPage.tsx
//
// Detail surface for ONE collection: a tree on the left, the selected file on
// the right, read-only. There are no tabs, because there are no lanes — what
// someone wrote and what someone put there are the same kind of thing and live
// in the same folder (ADR knowledge-is-plain-files).
//
// Read-only is deliberate and load-bearing. Correcting a file happens in the
// user's own editor, reached from the FileActions bar; with no index behind the
// files, that edit is live on the very next read with nothing to reconcile
// (spec knowledge FR-061).
//
// The filter box narrows the tree by title/filename as you type, entirely
// client-side. Server-side retrieval has its own surfaces — `coffer__grep` for
// agents, `coffer knowledge grep` for the CLI — and duplicating it here would
// be a second search with different rules.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { KnowledgePreviewBody } from "./KnowledgePreviewBody";
import { KnowledgeTreeLevel } from "./KnowledgeTreeLevel";
import { useKnowledgeFile, useTidyCollection } from "./useKnowledge";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const collection = useParams<{ scope: string }>().scope ?? "";

  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const file = useKnowledgeFile(selected);
  const tidy = useTidyCollection(collection);

  const onTidy = () =>
    tidy.mutate(undefined, {
      onSuccess: () => toast.success(t("knowledge.detail.tidyDone")),
      onError: (e) => toast.error(translateApiError(t, e)),
    });

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{collection}</h1>
        <Button type="button" variant="outline" size="sm" onClick={onTidy} disabled={tidy.isPending}>
          {t("knowledge.detail.tidy")}
        </Button>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(16rem,22rem)_1fr]">
        <div className="space-y-2">
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("knowledge.detail.filterPlaceholder")}
            aria-label={t("knowledge.detail.filterPlaceholder")}
          />
          <nav aria-label={t("knowledge.detail.treeLabel")} className="rounded-md border p-2">
            <KnowledgeTreeLevel
              path={collection}
              depth={0}
              selectedPath={selected}
              filter={filter}
              onSelect={setSelected}
            />
          </nav>
        </div>

        <section className="min-w-0 rounded-md border">
          {selected === null ? (
            <p className="p-6 text-sm text-muted-foreground">
              {t("knowledge.detail.selectAFile")}
            </p>
          ) : file.isPending ? (
            <p className="p-6 text-sm text-muted-foreground">{t("common.loading")}</p>
          ) : file.error ? (
            <p className="p-6 text-sm text-destructive" role="alert">
              {translateApiError(t, file.error)}
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-3 border-b px-4 py-2">
                <p className="truncate text-sm text-muted-foreground">{file.data.path}</p>
                <FileActions filePath={file.data.file_path} />
              </div>
              {/* `overflow-auto` is what keeps a wide table or an unbreakable
                  code span inside this pane: without it the content has no
                  scroll container, so it stretches the grid column and the
                  whole page scrolls sideways. Same treatment as the skill
                  file viewer. */}
              <KnowledgePreviewBody
                text={file.data.body}
                className="max-h-[70vh] overflow-auto p-4"
              />
            </>
          )}
        </section>
      </div>
    </div>
  );
}
