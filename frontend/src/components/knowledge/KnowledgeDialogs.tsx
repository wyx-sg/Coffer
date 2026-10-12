// frontend/src/components/knowledge/KnowledgeDialogs.tsx — the Knowledge page's dialogs.
//
// New collection and Link an external folder are always available; Upload
// needs a collection Coffer keeps to land in, so it mounts only once one
// exists, and never offers a linked folder, which Coffer writes nothing into.
// People write through a document's Edit, agents by writing files.
import { KnowledgeCreateDialog } from "@/components/knowledge/KnowledgeCreateDialog";
import { KnowledgeLinkDialog } from "@/components/knowledge/KnowledgeLinkDialog";
import { KnowledgeUploadDialog } from "@/components/knowledge/KnowledgeUploadDialog";
import type { CollectionOut } from "@/lib/api/knowledgeTypes";

export type KnowledgeDialog = "create" | "upload" | "link" | null;

interface Props {
  dialog: KnowledgeDialog;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  /** The collection an upload defaults to. */
  initial: string | null;
}

export function KnowledgeDialogs({ dialog, onOpenChange, collections, initial }: Props) {
  const owned = collections.filter((c) => !c.linked);
  return (
    <>
      <KnowledgeCreateDialog open={dialog === "create"} onOpenChange={onOpenChange} />
      <KnowledgeLinkDialog open={dialog === "link"} onOpenChange={onOpenChange} />
      {owned.length > 0 ? (
        <KnowledgeUploadDialog
          open={dialog === "upload"}
          onOpenChange={onOpenChange}
          collections={owned}
          initial={owned.some((c) => c.name === initial) ? initial : null}
        />
      ) : null}
    </>
  );
}
