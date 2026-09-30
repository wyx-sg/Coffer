// frontend/src/components/knowledge/KnowledgeUploadDialog.tsx
//
// Upload a document into a collection (boards 5.1.17, 5.1.18, 5.1.23,
// 5.1.28): Coffer converts it to Markdown and it joins the collection's Inbox
// as an item, curated like any other (with no model it is written as a
// document on the spot). The original file is not kept. A file is dropped on
// the zone or chosen; its name, kind and size and the target collection show
// before anything is sent; converting is its own state. A file that cannot
// become text is refused in the dialog, beside the file, with what to do
// instead — a ZIP or anything over 20 MB before it is sent, a scanned PDF or
// an unsupported type once the daemon has looked at it.
import { useEffect, useRef, useState, type DragEvent } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { AlertCircle, FileText, Loader2, Upload, X } from "lucide-react";

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
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useUploadKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { cn, formatBytes } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  initial: string | null;
}

/** The upload bound (spec knowledge "Bound uploads and leave nothing behind
 *  on failure"). */
const MAX_BYTES = 20 * 1024 * 1024;

/** A file's kind as the dialog names it, from its extension. */
const KINDS: Record<string, string> = {
  pdf: "PDF",
  doc: "Word",
  docx: "Word",
  ppt: "PowerPoint",
  pptx: "PowerPoint",
  xls: "Excel",
  xlsx: "Excel",
  html: "HTML",
  htm: "HTML",
  csv: "CSV",
  md: "Markdown",
  markdown: "Markdown",
  txt: "Text",
  zip: "ZIP archive",
  epub: "EPUB",
};

function extensionOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i < 0 ? "" : name.slice(i + 1).toLowerCase();
}

interface Refusal {
  title: string;
  body: string;
}

/** Why a file is refused before it is sent, if it is. */
function refuseBeforeSending(t: TFunction, file: File): Refusal | null {
  if (extensionOf(file.name) === "zip") {
    return { title: t("knowledge.upload.zipTitle"), body: t("knowledge.upload.zipBody") };
  }
  if (file.size > MAX_BYTES) {
    return { title: t("knowledge.upload.tooLargeTitle"), body: t("knowledge.upload.tooLargeBody") };
  }
  return null;
}

/** The daemon's refusal, in the dialog's words. */
function refusalOf(t: TFunction, error: unknown, file: File | null): Refusal {
  if (error instanceof ApiError) {
    const reason = (error.details as { reason?: unknown } | undefined)?.reason;
    if (error.code === "KNOWLEDGE_UPLOAD_TOO_LARGE") {
      return {
        title: t("knowledge.upload.tooLargeTitle"),
        body: t("knowledge.upload.tooLargeBody"),
      };
    }
    if (reason === "scanned_pdf") {
      return { title: t("knowledge.upload.noTextTitle"), body: t("knowledge.upload.noTextBody") };
    }
    if (reason === "empty_conversion") {
      return {
        title: t("knowledge.upload.noTextAnyTitle"),
        body: t("knowledge.upload.noTextAnyBody"),
      };
    }
    if (reason === "unsupported_type") {
      const kind = file
        ? (KINDS[extensionOf(file.name)] ?? extensionOf(file.name).toUpperCase())
        : "";
      return {
        title: t("knowledge.upload.unsupportedTitle", { kind }),
        body: translateApiError(t, error),
      };
    }
  }
  return { title: t("knowledge.upload.failedTitle"), body: translateApiError(t, error) };
}

export function KnowledgeUploadDialog({ open, onOpenChange, collections, initial }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const upload = useUploadKnowledgeFile();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [collection, setCollection] = useState("");
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    if (open) {
      setFile(null);
      setCollection(initial ?? collections[0]?.name ?? "");
      upload.reset();
    }
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const choose = (chosen: File | null) => {
    setFile(chosen);
    upload.reset();
  };
  const early = file ? refuseBeforeSending(t, file) : null;
  const refusal = early ?? (upload.error ? refusalOf(t, upload.error, file) : null);

  const send = () => {
    if (!file || early) return;
    upload.mutate(
      { collection, file },
      {
        onSuccess: (doc) => {
          toast.success(
            doc.pending || !doc.path
              ? t("knowledge.upload.pending", { name: file.name, collection })
              : t("knowledge.upload.written", { name: file.name, path: doc.path }),
          );
          onOpenChange(false);
        },
      },
    );
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    choose(e.dataTransfer.files?.[0] ?? null);
  };

  const meta = file
    ? upload.isPending
      ? t("knowledge.upload.converting")
      : [KINDS[extensionOf(file.name)], formatBytes(file.size)].filter(Boolean).join(" · ")
    : "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.upload.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.upload.body")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {file ? (
            <div className="space-y-2">
              <div className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5">
                {upload.isPending ? (
                  <Loader2 className="size-4 shrink-0 animate-spin text-text-subtle" aria-hidden />
                ) : (
                  <FileText className="size-4 shrink-0 text-text-subtle" aria-hidden />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{file.name}</p>
                  <p className="text-xs text-text-subtle">{meta}</p>
                </div>
                {upload.isPending ? null : (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("knowledge.upload.remove")}
                    onClick={() => choose(null)}
                  >
                    <X aria-hidden />
                  </Button>
                )}
              </div>
              {refusal ? (
                <div
                  role="alert"
                  className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
                >
                  <AlertCircle className="mt-px size-3.5 shrink-0 text-danger" aria-hidden />
                  <div className="flex min-w-0 flex-col gap-[3px]">
                    <p className="text-sm font-label">{refusal.title}</p>
                    <p className="text-xs leading-[1.45] text-text-muted">{refusal.body}</p>
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn(
                "flex w-full flex-col items-center gap-1 rounded-lg border border-dashed border-border px-4 py-7 text-center transition-colors hover:bg-surface-hover",
                dragging && "border-accent bg-accent-soft",
              )}
            >
              <Upload className="size-5 text-text-subtle" aria-hidden />
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
              choose(chosen);
            }}
          />
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={send}
            disabled={!file || !collection || upload.isPending || refusal !== null}
          >
            {upload.isPending ? t("knowledge.upload.uploading") : t("knowledge.upload.button")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
