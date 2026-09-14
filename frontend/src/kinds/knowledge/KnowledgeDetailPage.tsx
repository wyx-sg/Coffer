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
// Reach (ScopeControl) lives in the header, as on every other scoped Resource's
// detail page: which agents this collection is exposed to is a property of the
// collection, not of the file open in the pane.
//
// The filter box narrows the tree by title/filename as you type, entirely
// client-side. Server-side retrieval has its own surfaces — `coffer__grep` for
// agents, `coffer knowledge grep` for the CLI — and duplicating it here would
// be a second search with different rules.
import { useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { KnowledgeUploadButton } from "@/components/knowledge/KnowledgeUploadButton";
import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useResource } from "@/lib/hooks/useResources";
import { KnowledgePreviewBody } from "./KnowledgePreviewBody";
import { KnowledgeSearchPanel } from "./KnowledgeSearchPanel";
import { KnowledgeTreeLevel } from "./KnowledgeTreeLevel";
import { useKnowledgeFile, useTidyCollection } from "./useKnowledge";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const collection = useParams<{ scope: string }>().scope ?? "";

  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const file = useKnowledgeFile(selected);
  const tidy = useTidyCollection(collection);
  // `enabled` is a generic Resource field, not on /knowledge/collections, so
  // the reach control's required prop comes from the single-resource read.
  const resource = useResource("knowledge", collection);

  // The folder an upload lands in "where the user is": the parent of the file
  // currently open, or the collection root when nothing is selected yet.
  // `directory` is relative to the COLLECTION root, matching `IngestService`.
  const uploadDirectory = useMemo(() => {
    if (!selected) return null;
    const idx = selected.lastIndexOf("/");
    const parent = idx === -1 ? collection : selected.slice(0, idx);
    return parent === collection ? null : parent.slice(collection.length + 1);
  }, [selected, collection]);

  const onTidy = () =>
    tidy.mutate(undefined, {
      onSuccess: () => toast.success(t("knowledge.detail.tidyDone")),
      onError: (e) => toast.error(translateApiError(t, e)),
    });

  return (
    <div className="space-y-6 p-6">
      {/* The way back to the list, as every other detail page carries it. A
          collection is reached by clicking a row, so leaving it must not
          depend on the browser's own back button. */}
      <div className="-ml-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/knowledge")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" />
          {t("common.backTo", { label: t("nav.knowledge") })}
        </Button>
      </div>

      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">{collection}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {/* Reach sits in the header, exactly as every other kind's detail
              page carries it; passing no `scope` lets it fetch its own. */}
          <ScopeControl
            kind="knowledge"
            name={collection}
            enabled={resource.data?.enabled ?? true}
          />
          <KnowledgeUploadButton collection={collection} directory={uploadDirectory} />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onTidy}
            disabled={tidy.isPending}
          >
            {t("knowledge.detail.tidy")}
          </Button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(16rem,22rem)_1fr]">
        <div className="space-y-2">
          <KnowledgeSearchPanel collection={collection} onSelectPath={setSelected} />
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
