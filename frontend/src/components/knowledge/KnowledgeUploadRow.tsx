// frontend/src/components/knowledge/KnowledgeUploadRow.tsx
//
// One file in the Upload dialog (KnowledgeUploadDialog): its name, and under
// it its kind and size while it waits, "Converting to Markdown…" while it is
// sent, the source it became once saved; an icon for each state; a remove
// button while nothing is being sent; and, when it was refused — before
// sending or by the daemon — why, and what to do instead. And the zone files
// are dropped on or chosen from, smaller once some are listed.
import { useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle2, FileText, Loader2, Upload, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { extensionOf, KINDS, type Refusal } from "@/lib/knowledge/uploadChecks";
import { cn, formatBytes } from "@/lib/utils";

type UploadStatus = "ready" | "converting" | "saved" | "refused";

export interface UploadItem {
  id: number;
  file: File;
  status: UploadStatus;
  refusal: Refusal | null;
  /** The source it became, once saved. */
  path?: string;
  /** Refused by the daemon rather than before sending: Try again sends it again. */
  retryable?: boolean;
  /** Refused as a page already imported: Replace sends it again with `replace`. */
  replaceable?: boolean;
  replace?: boolean;
  /** Saved, but the import left these behind (missing or unsupported parts). */
  partial?: string[];
}

interface Props {
  item: UploadItem;
  removable: boolean;
  onRemove: () => void;
}

export function KnowledgeUploadRow({ item, removable, onRemove }: Props) {
  const { t } = useTranslation();
  const meta =
    item.status === "converting"
      ? t("knowledge.upload.converting")
      : item.status === "saved" && item.path
        ? t("knowledge.upload.savedAs", { path: item.path })
        : [KINDS[extensionOf(item.file.name)], formatBytes(item.file.size)]
            .filter(Boolean)
            .join(" · ");
  return (
    <li key={item.id} className="space-y-1.5" data-status={item.status}>
      <div className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5">
        {item.status === "converting" ? (
          <Loader2 className="size-4 shrink-0 animate-spin text-text-subtle" aria-hidden />
        ) : item.status === "saved" ? (
          <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden />
        ) : item.status === "refused" ? (
          <AlertCircle className="size-4 shrink-0 text-danger" aria-hidden />
        ) : (
          <FileText className="size-4 shrink-0 text-text-subtle" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs">{item.file.name}</p>
          <p className="truncate text-xs text-text-subtle">{meta}</p>
        </div>
        {removable ? (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("knowledge.upload.removeNamed", { name: item.file.name })}
            onClick={onRemove}
          >
            <X aria-hidden />
          </Button>
        ) : null}
      </div>
      {item.partial ? (
        <div
          role="status"
          data-testid="upload-partial"
          className="flex flex-col gap-[3px] rounded-lg bg-warning-soft px-3 py-2.5"
        >
          <p className="text-sm font-label">{t("knowledge.upload.partialTitle")}</p>
          <ul className="list-disc pl-4 text-xs leading-[1.45] text-text-muted">
            {item.partial.map((part) => (
              <li key={part}>{part}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {item.refusal ? (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
        >
          <div className="flex min-w-0 flex-col gap-[3px]">
            <p className="text-sm font-label">{item.refusal.title}</p>
            <p className="text-xs leading-[1.45] text-text-muted">{item.refusal.body}</p>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function KnowledgeUploadZone({
  more,
  disabled,
  onChoose,
  onFiles,
}: {
  /** Files are already listed: the zone is the smaller "Add more files". */
  more: boolean;
  disabled: boolean;
  onChoose: () => void;
  onFiles: (files: FileList) => void;
}) {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState(false);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    onFiles(e.dataTransfer.files);
  };
  return (
    <button
      type="button"
      onClick={onChoose}
      disabled={disabled}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex w-full flex-col items-center gap-1 rounded-lg border border-dashed border-border px-4 text-center transition-colors hover:bg-surface-hover disabled:pointer-events-none disabled:opacity-disabled",
        more ? "py-3" : "py-7",
        dragging && "border-accent bg-accent-soft",
      )}
    >
      <Upload className="size-5 text-text-subtle" aria-hidden />
      <span className="text-sm">
        {more ? t("knowledge.upload.chooseMore") : t("knowledge.upload.choose")}
      </span>
      {more ? null : (
        <span className="text-xs text-text-subtle">{t("knowledge.upload.types")}</span>
      )}
    </button>
  );
}

interface FooterProps {
  /** Every file is sent: the outcomes are on their rows. */
  done: boolean;
  running: boolean;
  ready: number;
  canSend: boolean;
  retryable: boolean;
  replaceable: boolean;
  onCancel: () => void;
  onRequeue: (flag: "retryable" | "replaceable") => void;
  onSend: () => void;
}

/** The dialog's buttons: Cancel or Close, Replace and Try again once a batch is
 *  done with files to send again, and Upload while files wait. */
export function KnowledgeUploadButtons(props: FooterProps) {
  const { t } = useTranslation();
  const { done, running, ready } = props;
  return (
    <>
      <Button variant="ghost" onClick={props.onCancel}>
        {done ? t("common.close") : t("common.cancel")}
      </Button>
      {done && props.replaceable ? (
        <Button variant="outline" onClick={() => props.onRequeue("replaceable")}>
          {t("knowledge.upload.replace")}
        </Button>
      ) : null}
      {done && props.retryable ? (
        <Button variant="outline" onClick={() => props.onRequeue("retryable")}>
          {t("common.tryAgain")}
        </Button>
      ) : null}
      {done ? null : (
        <Button onClick={props.onSend} disabled={!props.canSend}>
          {running
            ? t("knowledge.upload.uploading")
            : ready > 1
              ? t("knowledge.upload.buttonMany", { count: ready })
              : t("knowledge.upload.button")}
        </Button>
      )}
    </>
  );
}
