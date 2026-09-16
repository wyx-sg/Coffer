// frontend/src/pages/KnowledgeDetailPage.tsx
//
// Detail surface for ONE collection: the same two-pane file browser the skill
// detail page's Files tab is — a tree on the left, the selected file on the
// right, read-only. There are no tabs, because there are no lanes — what
// someone wrote and what someone put there are the same kind of thing and live
// in the same folder (ADR knowledge-is-plain-files).
//
// Read-only is deliberate and load-bearing. Correcting a file happens in the
// user's own editor, reached from the FileActions bar on the preview; with no
// index behind the files, that edit is live on the very next read with nothing
// to reconcile (spec knowledge FR-035).
//
// Reach (ScopeControl) lives in the header, as on every other scoped Resource's
// detail page: which agents this collection is exposed to is a property of the
// collection, not of the file open in the pane.
//
// The open file lives in the URL (`?file=`), so a reload or a shared link opens
// the same file — addressable state belongs to the router (.agents/frontend.md).
//
// The filter box narrows the tree by title/filename as you type, entirely
// client-side — it is the tree's own narrowing, not a search. Reading the files
// themselves has its own surfaces — `coffer__search` and `coffer__grep` for
// agents, `coffer knowledge search|grep` for the CLI — and a box in this page
// that queried the server was a second retrieval surface with its own rules,
// answering in a list that sat where the tree should be.
import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { FileActions } from "@/components/FileActions";
import { FILE_PANE_MAX_HEIGHT } from "@/components/filePane";
import { cn } from "@/lib/utils";
import { KnowledgeFileDelete } from "@/components/knowledge/KnowledgeFileDelete";
import { KnowledgeUploadButton } from "@/components/knowledge/KnowledgeUploadButton";
import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { translateApiError } from "@/lib/api/errors";
import { useResource } from "@/lib/hooks/useResources";
import { KnowledgePreviewBody } from "@/components/knowledge/KnowledgePreviewBody";
import { KnowledgeTreeLevel } from "@/components/knowledge/KnowledgeTreeLevel";
import { useKnowledgeFile, useTidyCollection } from "@/lib/hooks/useKnowledge";
import { useUpkeepRunning } from "@/lib/hooks/useUpkeep";

export function KnowledgeDetailPage() {
  const { t } = useTranslation();
  const collection = useParams<{ name: string }>().name ?? "";
  const [params, setParams] = useSearchParams();
  const selected = params.get("file");
  const setSelected = (path: string | null) =>
    setParams(
      (prev) => {
        if (path) prev.set("file", path);
        else prev.delete("file");
        return prev;
      },
      { replace: true },
    );

  const [filter, setFilter] = useState("");

  const file = useKnowledgeFile(selected);
  const tidy = useTidyCollection(collection);
  // Same treatment as memory's organise button, and for the same reason:
  // whether a pass is running is the DAEMON's answer, so leaving the page
  // mid-pass and coming back shows the pass, not an idle button inviting a
  // second concurrent rewrite of the same files. The mutation's own pending
  // state covers the moment between the click and the first poll.
  const tidyRunning = useUpkeepRunning("knowledge", collection);
  const tidying = tidy.isPending || tidyRunning;
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

  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: "/knowledge", label: t("common.backTo", { label: t("nav.knowledge") }) }}
        title={collection}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {/* Reach sits in the header, exactly as every other kind's detail
                page carries it; passing no `scope` lets it fetch its own. */}
            <ScopeControl
              kind="knowledge"
              name={collection}
              enabled={resource.data?.enabled ?? true}
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => tidy.mutate()}
                  disabled={tidying}
                >
                  <RefreshCw
                    className={tidying ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"}
                  />
                  {t("knowledge.detail.tidy")}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t("knowledge.detail.tidyHint")}</TooltipContent>
            </Tooltip>
            <KnowledgeUploadButton collection={collection} directory={uploadDirectory} />
          </div>
        }
      />

      {/* The skill Files tab's proportions, so the two browsers sit the same
          way on the page. */}
      <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
        <div className="space-y-2">
          <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t("knowledge.detail.treeLabel")}
          </p>
          <Input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("knowledge.detail.filterPlaceholder")}
            aria-label={t("knowledge.detail.filterPlaceholder")}
          />
          <nav aria-label={t("knowledge.detail.treeLabel")} className={FILE_PANE_MAX_HEIGHT}>
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
            <p className="p-6 text-sm text-muted-foreground">{t("knowledge.detail.selectAFile")}</p>
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
                <div className="flex flex-wrap items-center gap-2">
                  <FileActions filePath={file.data.file_path} />
                  {/* Last, after the actions that take the file elsewhere —
                      the same order every detail page puts delete in. It is
                      mounted only while a file is previewed, which is what
                      makes the path it names certain. */}
                  <KnowledgeFileDelete path={file.data.path} onDeleted={() => setSelected(null)} />
                </div>
              </div>
              {/* `overflow-auto` is what keeps a wide table or an unbreakable
                  code span inside this pane: without it the content has no
                  scroll container, so it stretches the grid column and the
                  whole page scrolls sideways. Same treatment as the skill
                  file viewer. */}
              <KnowledgePreviewBody
                text={file.data.body}
                className={cn(FILE_PANE_MAX_HEIGHT, "p-4")}
              />
            </>
          )}
        </section>
      </div>

    </div>
  );
}
