// frontend/src/components/files/FileTextEditor.tsx — the one text editor for a
// file's body.
//
// Knowledge documents, memories and skill files edit text the same way: a
// monospace textarea over the file's body, a danger banner when a save was
// refused as stale (or the error the save raised), ⌘S / Ctrl+S to save and
// Escape to discard while the textarea has focus — keys on the editor, not
// global handlers. This is that, once.
//
// What differs is passed in: an optional read-only `header` above the text (the
// knowledge editor's frontmatter grid), the conflict banner (the shared
// FileConflictBanner from `conflict`, or a `banner` of the caller's own — the
// skill editor's), and a `variant` — "surface" for the document panes, "code"
// for the skill file viewer's code background. The caller owns the draft
// (`useFileDraft`) and the buttons that Save and Discard.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { FileConflictBanner } from "@/components/FileConflictBanner";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

interface FileConflict {
  title: string;
  /** The banner's sentence, saying the text is not saved. */
  text: string;
  onCompare: () => void;
  onCopyMine: () => void;
  /** Take the disk's version, dropping the draft (asked first, by the banner). */
  onReload: () => void;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  /** A save was refused as stale: the banner shows and ⌘S does nothing. */
  isConflict?: boolean;
  /** The draft differs from what was loaded: ⌘S saves only then. */
  dirty: boolean;
  saving?: boolean;
  /** The last save's error, shown when it is not a conflict. */
  error?: unknown;
  /** The shared conflict banner. */
  conflict?: FileConflict;
  /** A conflict banner of the caller's own, instead of `conflict`. */
  banner?: ReactNode;
  /** Read-only content above the text, inside the same frame. */
  header?: ReactNode;
  variant?: "surface" | "code";
  onSave: () => void;
  /** Discard, asking first when the draft has changes. */
  onDiscard: () => void;
  /** Below the frame — a line of help. */
  children?: ReactNode;
  className?: string;
}

export function FileTextEditor({
  value,
  onChange,
  ariaLabel,
  isConflict = false,
  dirty,
  saving = false,
  error,
  conflict,
  banner,
  header,
  variant = "surface",
  onSave,
  onDiscard,
  children,
  className,
}: Props) {
  const { t } = useTranslation();
  const code = variant === "code";

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", code ? "gap-3" : "gap-2.5", className)}>
      {isConflict ? (
        (banner ?? (conflict ? <FileConflictBanner {...conflict} /> : null))
      ) : error ? (
        <p role="alert" className="shrink-0 text-sm text-danger">
          {translateApiError(t, error)}
        </p>
      ) : null}

      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border",
          code &&
            "focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent-soft",
        )}
      >
        {header}
        <textarea
          aria-label={ariaLabel}
          className={cn(
            "min-h-0 w-full flex-1 resize-none font-mono text-xs text-text outline-none",
            code ? "bg-code p-3 leading-[1.6]" : "bg-surface-raised px-4 py-3.5 leading-[1.7]",
          )}
          value={value}
          spellCheck={false}
          autoFocus
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
              e.preventDefault();
              if (dirty && !saving && !isConflict) onSave();
            } else if (e.key === "Escape") {
              e.preventDefault();
              onDiscard();
            }
          }}
        />
      </div>
      {children}
    </div>
  );
}
