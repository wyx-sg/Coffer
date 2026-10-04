// frontend/src/components/knowledge/KnowledgeDialogs.tsx — the Knowledge page's two dialogs.
//
// New collection is always available; Upload needs a collection to land in, so
// it mounts only once one exists. People write through a document's Edit,
// agents by writing files.
import { KnowledgeCreateDialog } from "@/components/knowledge/KnowledgeCreateDialog";
import { KnowledgeUploadDialog } from "@/components/knowledge/KnowledgeUploadDialog";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";

export type KnowledgeDialog = "create" | "upload" | null;

interface Props {
  dialog: KnowledgeDialog;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  /** The collection an upload defaults to. */
  initial: string | null;
}

export function KnowledgeDialogs({ dialog, onOpenChange, collections, initial }: Props) {
  return (
    <>
      <KnowledgeCreateDialog open={dialog === "create"} onOpenChange={onOpenChange} />
      {collections.length > 0 ? (
        <KnowledgeUploadDialog
          open={dialog === "upload"}
          onOpenChange={onOpenChange}
          collections={collections}
          initial={initial}
        />
      ) : null}
    </>
  );
}
