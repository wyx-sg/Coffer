// frontend/src/components/knowledge/KnowledgeLoadedDocument.tsx
//
// A file whose read has loaded (boards 5.1.01, 5.1.29): the pane bar — where
// it is, then History, Preview / Source, Open in editor and the ⋯ menu (Reveal
// in Finder, Delete) — and under it the read-only reader. History takes the
// whole Knowledge area in its place (KnowledgeHistoryView). Nothing here edits:
// a person changes a file in their own editor and the next read shows it. A
// linked folder's file has no History and no Delete: its own tools keep it.
import { useState } from "react";

import { useDeleteDocument } from "@/components/knowledge/KnowledgeDeleteDocument";
import { ReadingActions, type DocumentView } from "@/components/knowledge/KnowledgeDocumentActions";
import { KnowledgeDocumentReader } from "@/components/knowledge/KnowledgeDocumentReader";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import type { CollectionOut, FileOut } from "@/lib/api/knowledge";
import { useFileActionItems } from "@/lib/fileActionItems";
import { crumbsOf } from "@/lib/knowledge/crumbs";
import { useOpenInObsidian } from "@/lib/knowledge/obsidian";

interface LoadedProps {
  collection: CollectionOut;
  file: FileOut;
  onHistory: () => void;
}

export function KnowledgeLoadedDocument({ collection, file, onHistory }: LoadedProps) {
  const removeDocument = useDeleteDocument(collection.uid);
  const fileActions = useFileActionItems(file.file_path);
  const obsidian = useOpenInObsidian(file.file_path);
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
            onDelete={collection.linked ? null : () => removeDocument(file.path)}
            onHistory={collection.linked ? null : onHistory}
            obsidian={obsidian}
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
      </div>
    </div>
  );
}
