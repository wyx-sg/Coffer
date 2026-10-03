// frontend/src/components/files/FileStates.tsx
//
// The two states a file viewer shows instead of (or over) a file's text
// (canvas 4.3.15, 4.3.16): a binary file — "Can't preview binary file", its
// name and size, and Reveal in Finder — and the 32px grey bar over a file read
// only in part, with Open in editor; agents still get all of it.
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";

/** A binary file: no preview, only where it is. */
export function BinaryPane({
  name,
  size,
  onReveal,
}: {
  name: string;
  size: number;
  onReveal?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 p-4 text-center">
      <p className="text-sm font-label text-text">{t("files.binaryTitle")}</p>
      <p className="font-mono text-2xs text-text-subtle">
        {name} · {formatBytes(size)}
      </p>
      {onReveal ? (
        <Button variant="outline" size="sm" className="mt-2" onClick={onReveal}>
          <FolderOpen aria-hidden /> {t("fileActions.reveal")}
        </Button>
      ) : null}
    </div>
  );
}

/** The 32px bar over a file read only in part. */
export function TruncatedBar({
  shown,
  total,
  onOpenInEditor,
}: {
  shown: number;
  total: number;
  onOpenInEditor?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex h-8 shrink-0 items-center gap-2 border-b border-border-subtle bg-surface-sunken px-3 text-xs text-text-muted">
      {t("files.truncatedBar", { shown: formatBytes(shown), total: formatBytes(total) })}
      {onOpenInEditor ? (
        <button
          type="button"
          onClick={onOpenInEditor}
          className="ml-auto whitespace-nowrap font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          {t("fileActions.openInEditor")}
        </button>
      ) : null}
    </div>
  );
}
