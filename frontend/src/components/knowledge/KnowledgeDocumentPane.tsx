// frontend/src/components/knowledge/KnowledgeDocumentPane.tsx
//
// One open file (boards 5.1.01, 5.1.05, 5.1.29): the bar — where it is
// (collection › folders › file, full path) and its actions — over the reader,
// with no tabs. History opens a drawer beside the file (spec knowledge "Show a
// collection as one tree of read-only documents in the web UI"), named in the
// address as `history=1` so it survives a reload and a link can open it; the
// file stays in view while it is open. The drawer reads on its own, so a
// history that cannot be read leaves the file working, and a file that cannot
// be read still shows its history.
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { KnowledgeHistoryDrawer } from "@/components/knowledge/KnowledgeHistoryDrawer";
import { KnowledgeLoadedDocument } from "@/components/knowledge/KnowledgeLoadedDocument";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { crumbsOf } from "@/lib/knowledge/crumbs";
import { HISTORY_PARAM } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  /** Knowledge-root-relative path of the open file. */
  path: string;
}

export function KnowledgeDocumentPane({ collection, path }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);
  const [params, setParams] = useSearchParams();
  const historyOpen = params.get(HISTORY_PARAM) === "1";

  const setHistory = (open: boolean) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (open) next.set(HISTORY_PARAM, "1");
        else next.delete(HISTORY_PARAM);
        return next;
      },
      { replace: true },
    );
  const drawer = historyOpen ? (
    <KnowledgeHistoryDrawer path={path} onClose={() => setHistory(false)} />
  ) : null;

  if (file.data) {
    return (
      <KnowledgeLoadedDocument
        collection={collection}
        file={file.data}
        historyOpen={historyOpen}
        onHistory={() => setHistory(!historyOpen)}
        drawer={drawer}
      />
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar crumbs={crumbsOf(collection, path)} />
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 px-10 py-6">
          {file.error ? (
            <p className="text-sm text-danger" role="alert">
              {translateApiError(t, file.error)}
            </p>
          ) : (
            <div className="space-y-3" aria-busy>
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          )}
        </div>
        {drawer}
      </div>
    </div>
  );
}
