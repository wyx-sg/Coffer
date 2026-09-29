// frontend/src/components/knowledge/KnowledgeUploadDialog.tsx
//
// Upload a document into a collection: Coffer converts it to Markdown and it
// joins the collection's Inbox as an item, curated like any other (with no
// model it is written as a document on the spot). The original file is not
// kept. The chosen file, its size and the target collection are shown before
// anything is sent; converting is its own state; a file that cannot be
// converted is refused in the dialog, beside the file, with what to do.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileUp, X } from "lucide-react";

import { KnowledgeCollectionSelect } from "@/components/knowledge/KnowledgeCollectionSelect";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useUploadKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { formatBytes } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  initial: string | null;
}

export function KnowledgeUploadDialog({ open, onOpenChange, collections, initial }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const upload = useUploadKnowledgeFile();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [collection, setCollection] = useState("");

  useEffect(() => {
    if (open) {
      setFile(null);
      setCollection(initial ?? collections[0]?.name ?? "");
      upload.reset();
    }
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const send = () => {
    if (!file) return;
    upload.mutate(
      { collection, file },
      {
        onSuccess: (doc) => {
          toast.success(
            doc.pending || !doc.path
              ? t("knowledge.upload.pending", { title: doc.title })
              : t("knowledge.upload.written", { title: doc.title, path: doc.path }),
          );
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.upload.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.upload.body")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {file ? (
            <div className="flex items-center gap-3 rounded-md border border-border px-3 py-2">
              <FileUp className="size-4 shrink-0 text-text-subtle" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{file.name}</p>
                <p className="text-xs text-text-subtle">
                  {upload.isPending ? t("knowledge.upload.converting") : formatBytes(file.size)}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("knowledge.upload.remove")}
                disabled={upload.isPending}
                onClick={() => {
                  setFile(null);
                  upload.reset();
                }}
              >
                <X aria-hidden />
              </Button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="flex w-full flex-col items-center gap-1 rounded-md border border-dashed border-border px-4 py-6 text-center hover:bg-surface-hover"
            >
              <FileUp className="size-5 text-text-subtle" aria-hidden />
              <span className="text-sm">{t("knowledge.upload.choose")}</span>
              <span className="text-xs text-text-subtle">{t("knowledge.upload.types")}</span>
            </button>
          )}
          <input
            ref={input}
            type="file"
            className="hidden"
            aria-label={t("knowledge.upload.choose")}
            onChange={(e) => {
              const chosen = e.target.files?.[0] ?? null;
              e.target.value = "";
              setFile(chosen);
              upload.reset();
            }}
          />
          {upload.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, upload.error)}
            </p>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-upload-collection" required>
              {t("knowledge.upload.into")}
            </Label>
            <KnowledgeCollectionSelect
              id="knowledge-upload-collection"
              collections={collections}
              value={collection}
              onChange={setCollection}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={send} disabled={!file || !collection || upload.isPending}>
            {upload.isPending ? t("knowledge.upload.uploading") : t("knowledge.upload.button")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
