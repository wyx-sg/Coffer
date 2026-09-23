// frontend/src/components/knowledge/KnowledgeUploadButton.tsx
//
// Upload one document into the collection currently in view (spec knowledge
// "Convert uploads into material without keeping them" and "Promote material
// directly when no model is configured"). An upload is MATERIAL, not a document: its extracted
// Markdown joins the collection's inbox and the next curation pass merges it
// into the documents — or, with no internal model configured, it is promoted
// to a document on the spot. The two outcomes look nothing alike on the page
// (a document appears in the tree, or only the pending count moves), so the
// toast says which one happened rather than a bare "uploaded".
//
// There is no folder to aim at: where merged knowledge belongs is curation's
// call, and a promoted upload lands at the collection's top level.
//
// A hidden `<input type="file">` behind a visible button, mirroring
// SyncMasterKeyCard's key import: the browser reads the bytes directly, so
// there is no native dialog to drive. On success the tree and the counts
// refresh themselves — `useUploadKnowledgeFile` invalidates the whole
// `["knowledge"]` subtree — so this component only fires the mutation and
// reports the outcome. On failure `translateApiError` already carries a
// one-line, never-a-raw-code message for both documented failures
// (`INGEST_REJECTED` names the unsupported type; `KNOWLEDGE_UPLOAD_TOO_LARGE`
// says the file was too large).
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useUploadKnowledgeFile } from "@/lib/hooks/useKnowledge";

interface Props {
  /** The collection's NAME — its directory, which is what an upload names. */
  collection: string;
}

export function KnowledgeUploadButton({ collection }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = useUploadKnowledgeFile();

  const onFileChosen = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(
      { collection, file },
      {
        onSuccess: (doc) =>
          toast.success(
            doc.pending || !doc.path
              ? t("knowledge.upload.pending", { title: doc.title })
              : t("knowledge.upload.written", { title: doc.title, path: doc.path }),
          ),
      },
    );
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => fileInput.current?.click()}
        disabled={upload.isPending}
      >
        <Upload className="mr-1.5 size-3.5" />
        {upload.isPending ? t("knowledge.upload.uploading") : t("knowledge.upload.button")}
      </Button>
      {/* Hidden on purpose: the Button above is the affordance. */}
      <input
        ref={fileInput}
        type="file"
        className="hidden"
        aria-label={t("knowledge.upload.button")}
        onChange={(e) => {
          const file = e.target.files?.[0];
          // Reset first, so re-picking the SAME file fires change again.
          e.target.value = "";
          onFileChosen(file);
        }}
      />
    </>
  );
}
