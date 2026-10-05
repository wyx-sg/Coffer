// frontend/src/components/knowledge/KnowledgeLoadedDocument.tsx
//
// A document whose file has loaded (boards 5.1.01, 5.1.29): the pane bar with
// its Document / History tabs and the document's actions — Preview / Source,
// Open in editor, and the ⋯ menu (Reveal in Finder, Delete document) — and
// under it the read-only reader. Nothing here edits: a person changes a
// document in their own editor and the next read shows it.
import { useState, type ReactNode } from "react";

import { useDeleteDocument } from "@/components/knowledge/KnowledgeDeleteDocument";
import { ReadingActions, type DocumentView } from "@/components/knowledge/KnowledgeDocumentActions";
import { KnowledgeDocumentReader } from "@/components/knowledge/KnowledgeDocumentReader";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import type { CollectionOut, FileOut } from "@/lib/api/knowledge";
import { useFileActionItems } from "@/lib/fileActionItems";
import { crumbsOf } from "@/lib/knowledge/crumbs";

interface LoadedProps {
  collection: CollectionOut;
  file: FileOut;
  /** The Document / History tabs, drawn beside the crumbs. */
  tabs: ReactNode;
}

export function KnowledgeLoadedDocument({ collection, file, tabs }: LoadedProps) {
  const removeDocument = useDeleteDocument(collection.uid);
  const fileActions = useFileActionItems(file.file_path);
  const [view, setView] = useState<DocumentView>("preview");
  const markdown = /\.(md|markdown)$/i.test(file.path);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar
        crumbs={crumbsOf(collection, file.path)}
        tabs={tabs}
        actions={
          <ReadingActions
            path={file.path}
            markdown={markdown}
            view={markdown ? view : "source"}
            onView={setView}
            fileActions={fileActions}
            onDelete={() => removeDocument(file.path)}
          />
        }
      />
      <KnowledgeDocumentReader file={file} source={!markdown || view === "source"} />
    </div>
  );
}
