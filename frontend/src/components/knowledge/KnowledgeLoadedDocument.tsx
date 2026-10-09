// frontend/src/components/knowledge/KnowledgeLoadedDocument.tsx
//
// A file whose read has loaded (boards 5.1.01, 5.1.29): the pane bar — where
// it is, then History, Preview / Source, Open in editor and the ⋯ menu (Reveal
// in Finder, Delete) — and under it the read-only reader, with the history
// drawer beside it while it is open. Nothing here edits: a person changes a
// file in their own editor and the next read shows it.
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
  historyOpen: boolean;
  onHistory: () => void;
  /** The history drawer, drawn beside the reader while open. */
  drawer: ReactNode;
}

export function KnowledgeLoadedDocument({
  collection,
  file,
  historyOpen,
  onHistory,
  drawer,
}: LoadedProps) {
  const removeDocument = useDeleteDocument(collection.uid);
  const fileActions = useFileActionItems(file.file_path);
  const [view, setView] = useState<DocumentView>("preview");
  const markdown = /\.(md|markdown)$/i.test(file.path);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar
        crumbs={crumbsOf(collection, file.path)}
        actions={
          <ReadingActions
            path={file.path}
            markdown={markdown}
            view={markdown ? view : "source"}
            onView={setView}
            fileActions={fileActions}
            onDelete={() => removeDocument(file.path)}
            historyOpen={historyOpen}
            onHistory={onHistory}
          />
        }
      />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <KnowledgeDocumentReader
            file={file}
            collectionUid={collection.uid}
            source={!markdown || view === "source"}
          />
        </div>
        {drawer}
      </div>
    </div>
  );
}
