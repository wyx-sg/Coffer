// frontend/src/components/knowledge/KnowledgeUploadButton.tsx
//
// Upload one document into the collection currently in view — always into its
// `sources/` lane, and into a folder inside that lane when the caller names one
// (spec knowledge FR-023/FR-061). An upload is a source like any other, so
// there is no lane to choose and no way to aim one at `topics/`. A hidden
// `<input type="file">` behind a visible button, mirroring
// SyncMasterKeyCard's key import: the browser reads the bytes directly, so
// there is no native dialog to drive. On success the tree refreshes itself —
// `useUploadKnowledgeFile` invalidates the whole `["knowledge"]` subtree — so
// this component only fires the mutation and reports the outcome. On failure
// `translateApiError` already carries a one-line, never-a-raw-code message
// for both documented failures (`INGEST_REJECTED` names the unsupported type;
// `KNOWLEDGE_UPLOAD_TOO_LARGE` says the file was too large).
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useUploadKnowledgeFile } from "@/lib/hooks/useKnowledge";

interface Props {
  collection: string;
  /** Folder inside the collection's `sources/` the caller is viewing, if any. */
  folder?: string | null;
}

export function KnowledgeUploadButton({ collection, folder }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const upload = useUploadKnowledgeFile();

  const onFileChosen = (file: File | undefined) => {
    if (!file) return;
    upload.mutate(
      { collection, folder, file },
      { onSuccess: (doc) => toast.success(t("knowledge.upload.success", { title: doc.title })) },
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
