// frontend/src/components/knowledge/KnowledgeLoadedDocument.tsx
//
// A document whose file has loaded (boards 5.1.01, 5.1.29): the pane bar with
// the document's actions — Preview / Source, Open in editor, and the ⋯ menu
// (Reveal in Finder, History…, Delete document) — and under it the read-only
// reader. Nothing here edits: a person changes a document in their own editor
// and the next read shows it. History… opens the shared dialog for the
// document's path in the vault (`knowledge/<collection>/…`).
import { useState } from "react";

import { useDeleteDocument } from "@/components/knowledge/KnowledgeDeleteDocument";
import { ReadingActions, type DocumentView } from "@/components/knowledge/KnowledgeDocumentActions";
import { KnowledgeDocumentReader } from "@/components/knowledge/KnowledgeDocumentReader";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { VaultHistoryDialog } from "@/components/vault/VaultHistoryDialog";
import type { CollectionOut, FileOut } from "@/lib/api/knowledge";
import { useFileActionItems } from "@/lib/fileActionItems";
import { crumbsOf } from "@/lib/knowledge/crumbs";
import { vaultPathOf } from "@/lib/knowledge/routes";

interface LoadedProps {
  collection: CollectionOut;
  file: FileOut;
}

export function KnowledgeLoadedDocument({ collection, file }: LoadedProps) {
  const removeDocument = useDeleteDocument(collection.uid);
  const fileActions = useFileActionItems(file.file_path);
  const [view, setView] = useState<DocumentView>("preview");
  const [historyOpen, setHistoryOpen] = useState(false);
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
            onHistory={() => setHistoryOpen(true)}
            onDelete={() => removeDocument(file.path)}
          />
        }
      />
      <KnowledgeDocumentReader file={file} source={!markdown || view === "source"} />
      <VaultHistoryDialog
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        path={vaultPathOf(file.path)}
      />
    </div>
  );
}
