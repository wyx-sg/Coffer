// frontend/src/components/knowledge/KnowledgeDialogs.tsx — the Knowledge page's three dialogs.
//
// Create a collection is always available; Add a document and Upload need a
// collection to land in, so they mount only once one exists.
import { KnowledgeAddDocumentDialog } from "@/components/knowledge/KnowledgeAddDocumentDialog";
import { KnowledgeCreateDialog } from "@/components/knowledge/KnowledgeCreateDialog";
import { KnowledgeUploadDialog } from "@/components/knowledge/KnowledgeUploadDialog";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";

export type KnowledgeDialog = "create" | "add" | "upload" | null;

interface Props {
  dialog: KnowledgeDialog;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  /** The collection a new document or upload defaults to. */
  initial: string | null;
  modelSet: boolean | undefined;
}

export function KnowledgeDialogs({ dialog, onOpenChange, collections, initial, modelSet }: Props) {
  return (
    <>
      <KnowledgeCreateDialog open={dialog === "create"} onOpenChange={onOpenChange} />
      {collections.length > 0 ? (
        <>
          <KnowledgeAddDocumentDialog
            open={dialog === "add"}
            onOpenChange={onOpenChange}
            collections={collections}
            initial={initial}
            modelSet={modelSet}
          />
          <KnowledgeUploadDialog
            open={dialog === "upload"}
            onOpenChange={onOpenChange}
            collections={collections}
            initial={initial}
          />
        </>
      ) : null}
    </>
  );
}
