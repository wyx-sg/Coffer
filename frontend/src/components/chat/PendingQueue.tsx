// components/chat/PendingQueue.tsx
// The queued-messages strip shown above the composer: messages sent while a turn
// is still streaming wait here (they queue server-side). Each row shows the full
// (wrapped, clamped) text plus edit — pull it back into the composer to amend —
// and remove controls. Extracted from MessageThread to keep that file within the
// component size budget (agents/stack.md).
import { useTranslation } from "react-i18next";
import { Pencil, X } from "lucide-react";

interface Props {
  /** Messages queued behind the in-flight turn, in order. */
  pending: string[];
  /** Pull the queued message at `index` back into the composer to amend. */
  onEdit: (index: number) => void;
  /** Drop the queued message at `index`. */
  onRemove: (index: number) => void;
}

export function PendingQueue({ pending, onEdit, onRemove }: Props) {
  const { t } = useTranslation();
  if (pending.length === 0) return null;
  return (
    <div className="flex max-h-40 flex-col gap-1 overflow-y-auto border-t border-border bg-background px-4 pt-2">
      <span className="text-xs text-muted-foreground">{t("chat.queue.label")}</span>
      {pending.map((text, idx) => (
        <div
          key={`${idx}-${text}`}
          className="flex items-start gap-2 rounded-md bg-secondary px-2 py-1 text-xs text-secondary-foreground"
        >
          <span
            className="line-clamp-2 min-w-0 flex-1 whitespace-pre-wrap break-words"
            title={text}
          >
            {text}
          </span>
          <button
            type="button"
            className="shrink-0 rounded p-0.5 hover:text-foreground"
            onClick={() => onEdit(idx)}
            aria-label={t("chat.queue.edit")}
          >
            <Pencil className="size-3" />
          </button>
          <button
            type="button"
            className="shrink-0 rounded p-0.5 hover:text-destructive"
            onClick={() => onRemove(idx)}
            aria-label={t("chat.queue.remove")}
          >
            <X className="size-3" />
          </button>
        </div>
      ))}
    </div>
  );
}
