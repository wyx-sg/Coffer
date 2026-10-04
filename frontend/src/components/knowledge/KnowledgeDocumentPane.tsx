// frontend/src/components/knowledge/KnowledgeDocumentPane.tsx
//
// One open document (boards 5.1.01–5.1.04, 5.1.29): reads the file, and while
// it loads shows the bar — where it is (collection › folders › file, full
// path) and its two tabs, Document and History (every version, who wrote it,
// its diff, restore; spec web-ui "Show a knowledge document's history on its
// History tab"). The tab is in the path (`/knowledge/<uid>/history?file=`); a
// History that cannot be read leaves the Document tab working, because each
// tab reads on its own. KnowledgeLoadedDocument takes over once the file is in.
import { useTranslation } from "react-i18next";

import { KnowledgeLoadedDocument } from "@/components/knowledge/KnowledgeLoadedDocument";
import { KnowledgePaneBar, PaneBarTab } from "@/components/knowledge/KnowledgePaneBar";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { crumbsOf } from "@/lib/knowledge/crumbs";
import { collectionPath } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  /** Knowledge-root-relative path of the open document. */
  path: string;
  tab: "document" | "history";
}

export function KnowledgeDocumentPane({ collection, path, tab }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);

  const tabs = (
    <nav
      aria-label={t("knowledge.document.views")}
      className="ml-[18px] flex gap-[18px] self-stretch"
    >
      <PaneBarTab
        to={collectionPath(collection.uid, "document", path)}
        current={tab === "document"}
      >
        {t("knowledge.document.tab")}
      </PaneBarTab>
      <PaneBarTab to={collectionPath(collection.uid, "history", path)} current={tab === "history"}>
        {t("knowledge.history.tab")}
      </PaneBarTab>
    </nav>
  );

  if (!file.data) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbsOf(collection, path)} tabs={tabs} />
        <div className="px-10 py-6">
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
      </div>
    );
  }

  return (
    // Keyed by path: a draft belongs to one document only.
    <KnowledgeLoadedDocument
      key={file.data.path}
      collection={collection}
      file={file.data}
      tab={tab}
      tabs={tabs}
      reload={() => file.refetch()}
    />
  );
}
