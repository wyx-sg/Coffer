// frontend/src/components/knowledge/KnowledgeDocumentPane.tsx
//
// One open document: where it is (collection › folders › file), and its two
// tabs — Document (the default, the reader and the body editor) and History
// (every version, who wrote it, its diff, restore) — spec web-ui "Show a
// knowledge document's history on its History tab". The tab is in the path
// (`/knowledge/<uid>/history?file=`); a History that cannot be read leaves the
// Document tab working, because each tab reads on its own.
import { useTranslation } from "react-i18next";

import { KnowledgeDocumentView } from "@/components/knowledge/KnowledgeDocumentView";
import { KnowledgeHistoryTab } from "@/components/knowledge/KnowledgeHistoryTab";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { pathInCollection } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  /** Knowledge-root-relative path of the open document. */
  path: string;
  tab: "document" | "history";
  setTab: (tab: string) => void;
}

export function KnowledgeDocumentPane({ collection, path, tab, setTab }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);
  const crumbs = pathInCollection(path).split("/");

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <nav
        aria-label={t("knowledge.document.where")}
        className="flex flex-wrap items-center gap-1 text-xs text-text-subtle"
      >
        <span>{collection.title || collection.name}</span>
        {crumbs.map((c, i) => (
          <span key={i} className="flex items-center gap-1">
            <span aria-hidden>›</span>
            <span className={i === crumbs.length - 1 ? "text-text" : undefined}>{c}</span>
          </span>
        ))}
      </nav>

      <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col">
        <TabsList>
          <TabsTrigger value="document">{t("knowledge.document.tab")}</TabsTrigger>
          <TabsTrigger value="history">{t("knowledge.history.tab")}</TabsTrigger>
        </TabsList>
        <TabsContent value={tab} className="mt-3 flex min-h-0 flex-1 flex-col">
          {tab === "history" ? (
            <KnowledgeHistoryTab path={path} />
          ) : file.isPending ? (
            <div className="space-y-3" aria-busy>
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : file.error ? (
            <p className="text-sm text-danger" role="alert">
              {translateApiError(t, file.error)}
            </p>
          ) : (
            // Keyed by path: a draft belongs to one document only.
            <KnowledgeDocumentView
              key={file.data.path}
              collection={collection}
              file={file.data}
              reload={() => file.refetch()}
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
