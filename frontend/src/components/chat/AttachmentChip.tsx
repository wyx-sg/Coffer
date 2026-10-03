// components/chat/AttachmentChip.tsx
// One attached file as an inline chip: in the thread (name + type, read from the
// persisted reference) and in the composer (name + size, with uploading /
// failed states and a remove control). The path is never shown — the wire does
// not carry it (spec chat "Show a message's attachments in the thread"). An
// image with a `src` shows as a thumbnail instead of a chip.
import { useTranslation } from "react-i18next";
import { AlertCircle, FileText, Image as ImageIcon, Loader2, Paperclip, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  /** Display name; falls back to a generic "Attachment" label. */
  name?: string | null;
  /** Second line of meaning after the name — the type in the thread, the size in the composer. */
  detail?: string | null;
  /** Mime type, used only to pick the icon. */
  mime?: string | null;
  /** Composer upload state; omitted for a persisted attachment. */
  state?: "uploading" | "failed";
  /** Why a failed upload failed, already translated. */
  error?: string;
  /** Where an image's bytes can be fetched; with an image `mime` the chip becomes a thumbnail. */
  src?: string;
  /** Shown as an × button when given. */
  onRemove?: () => void;
}

function FileIcon({ mime }: { mime?: string | null }) {
  if (mime?.startsWith("image/")) return <ImageIcon className="size-3.5 shrink-0" aria-hidden />;
  if (mime) return <FileText className="size-3.5 shrink-0" aria-hidden />;
  return <Paperclip className="size-3.5 shrink-0" aria-hidden />;
}

export function AttachmentChip({ name, detail, mime, src, state, error, onRemove }: Props) {
  const { t } = useTranslation();
  const label = name || t("conversations.attachment");
  const failed = state === "failed";
  if (src && mime?.startsWith("image/") && !state) {
    return (
      <img
        data-testid="attachment-thumbnail"
        src={src}
        alt={label}
        title={label}
        loading="lazy"
        className="size-16 rounded-lg border border-border object-cover"
      />
    );
  }
  return (
    <div
      data-testid="attachment-chip"
      className={cn(
        "flex w-fit max-w-[min(20rem,100%)] items-center gap-1.5 rounded-md border bg-muted px-2 py-1 text-xs text-muted-foreground",
        failed ? "border-destructive text-destructive" : "border-border",
      )}
    >
      {state === "uploading" ? (
        <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
      ) : failed ? (
        <AlertCircle className="size-3.5 shrink-0" aria-hidden />
      ) : (
        <FileIcon mime={mime} />
      )}
      <span className="min-w-0 truncate text-foreground">{label}</span>
      {detail && !(failed && error) ? <span className="shrink-0 opacity-70">{detail}</span> : null}
      {state === "uploading" ? (
        <span className="shrink-0">{t("conversations.attachments.uploading")}</span>
      ) : failed && error ? (
        <span className="min-w-0 truncate" role="alert">
          {error}
        </span>
      ) : null}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={t("conversations.attachments.remove", { name: label })}
          className="-mr-0.5 shrink-0 rounded-sm p-0.5 hover:bg-surface-hover hover:text-text"
        >
          <X className="size-3" aria-hidden />
        </button>
      )}
    </div>
  );
}
