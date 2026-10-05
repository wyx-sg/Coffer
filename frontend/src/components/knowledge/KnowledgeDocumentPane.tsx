// frontend/src/components/knowledge/KnowledgeDocumentPane.tsx
//
// One open document (boards 5.1.01, 5.1.29): reads the file, and while it
// loads shows the bar — where it is (collection › folders › file, full path).
// A document has no tabs: it is read here and changed in the person's own
// editor (spec knowledge "Show a collection as one tree of read-only
// documents in the web UI"). KnowledgeLoadedDocument takes over once the file
// is in.
import { useTranslation } from "react-i18next";

import { KnowledgeLoadedDocument } from "@/components/knowledge/KnowledgeLoadedDocument";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { crumbsOf } from "@/lib/knowledge/crumbs";

interface Props {
  collection: CollectionOut;
  /** Knowledge-root-relative path of the open document. */
  path: string;
}

export function KnowledgeDocumentPane({ collection, path }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);

  if (!file.data) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbsOf(collection, path)} />
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

  return <KnowledgeLoadedDocument collection={collection} file={file.data} />;
}
