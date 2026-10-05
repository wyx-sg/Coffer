// frontend/src/components/knowledge/KnowledgeDocumentPane.tsx
//
// One open document (boards 5.1.01, 5.1.05, 5.1.29): the bar — where it is
// (collection › folders › file, full path) and its two tabs, Document and
// History — over the tab. Document reads the file read-only; the document is
// changed in the person's own editor (spec knowledge "Show a collection as one
// tree of read-only documents in the web UI"). History lists the document's
// versions from the vault's history and restores one (spec web-ui "Show a
// vault file's history on a History tab"). The tab is in the path
// (`/knowledge/<uid>/history?file=`), and each tab reads on its own, so a
// history that cannot be read leaves the Document tab working.
import { useTranslation } from "react-i18next";

import { VaultHistoryView } from "@/components/history/VaultHistoryView";
import { KnowledgeLoadedDocument } from "@/components/knowledge/KnowledgeLoadedDocument";
import { KnowledgePaneBar, PaneBarTab } from "@/components/knowledge/KnowledgePaneBar";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { crumbsOf } from "@/lib/knowledge/crumbs";
import { collectionPath, vaultPathOf, type KnowledgeTab } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  /** Knowledge-root-relative path of the open document. */
  path: string;
  tab: KnowledgeTab;
}

export function KnowledgeDocumentPane({ collection, path, tab }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);

  const tabs = (
    <nav
      aria-label={t("knowledge.document.views")}
      className="ml-[18px] flex shrink-0 gap-[18px] self-stretch"
    >
      <PaneBarTab to={collectionPath(collection.uid, path)} current={tab === "document"}>
        {t("knowledge.document.tabs.document")}
      </PaneBarTab>
      <PaneBarTab to={collectionPath(collection.uid, path, "history")} current={tab === "history"}>
        {t("knowledge.document.tabs.history")}
      </PaneBarTab>
    </nav>
  );

  if (tab === "history") {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbsOf(collection, path)} tabs={tabs} />
        <div className="flex min-h-0 flex-1 flex-col px-6 py-4">
          <VaultHistoryView path={vaultPathOf(path)} storageKey="knowledge-history" />
        </div>
      </div>
    );
  }

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

  return <KnowledgeLoadedDocument collection={collection} file={file.data} tabs={tabs} />;
}
