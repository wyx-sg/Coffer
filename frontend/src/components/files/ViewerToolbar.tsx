// frontend/src/components/files/ViewerToolbar.tsx
//
// The 40px toolbar over every file viewer (Foundations 0.6.03): the file's path
// in the mono face, shortened in the middle, and at the right — Preview /
// Source for a Markdown file (Preview first), a wrap toggle for code, "Open in
// editor", a Reveal icon, and whatever the viewer adds (Edit, or the unsaved
// state with Revert and Save). Only viewers that actually show a file's content
// carry it.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, WrapText } from "lucide-react";

import { middlePath } from "@/components/files/middlePath";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { useFileActionItems } from "@/lib/fileActionItems";
import { formatBytes } from "@/lib/utils";

export type FileView = "preview" | "source";

interface Props {
  /** The path as shown (home-abbreviated); shortened in the middle when long. */
  path: string;
  /** The whole path for the tooltip, when `path` is already shortened. */
  fullPath?: string;
  /** The absolute path the editor / Finder open. Without it the two buttons are left out. */
  absPath?: string;
  /** The file's size, beside its path. */
  size?: number;
  /** Markdown files: the Preview / Source toggle. */
  view?: { value: FileView; onChange: (view: FileView) => void };
  /** Code files: the wrap-lines toggle. */
  wrap?: { on: boolean; onChange: (on: boolean) => void };
  /** Leave out "Open in editor" (a list view, not a file). */
  noEditor?: boolean;
  /** Show the Reveal icon (the viewer is the only place the folder is offered). */
  reveal?: boolean;
  /** The path's state at its right end, before the actions: "● Unsaved changes". */
  status?: ReactNode;
  /** After the stock actions: Edit, Revert, Save, New file. */
  children?: ReactNode;
}

function FileButtons({
  absPath,
  noEditor,
  reveal,
}: {
  absPath: string;
  noEditor?: boolean;
  reveal?: boolean;
}) {
  const [open, revealItem] = useFileActionItems(absPath);
  return (
    <>
      {noEditor ? null : (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-text"
          onClick={open.onClick}
        >
          <open.icon aria-hidden /> {open.label}
        </Button>
      )}
      {reveal ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={revealItem.label}
          title={revealItem.label}
          onClick={revealItem.onClick}
        >
          <FolderOpen aria-hidden />
        </Button>
      ) : null}
    </>
  );
}

export function ViewerToolbar({
  path,
  fullPath,
  absPath,
  size,
  view,
  wrap,
  noEditor,
  reveal,
  status,
  children,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border-subtle bg-surface-raised px-3">
      <span title={fullPath ?? path} className="min-w-0 truncate font-mono text-xs text-text-muted">
        {middlePath(path)}
      </span>
      {size === undefined ? null : (
        <span className="shrink-0 text-xs text-text-subtle">{formatBytes(size)}</span>
      )}
      <span className="ml-auto inline-flex shrink-0 items-center gap-2">
        {status}
        {view ? (
          <Segmented
            label={t("files.viewLabel")}
            value={view.value}
            onChange={view.onChange}
            options={[
              { value: "preview", label: t("files.preview") },
              { value: "source", label: t("files.source") },
            ]}
          />
        ) : null}
        {wrap ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-pressed={wrap.on}
            aria-label={t("files.wrap")}
            title={t("files.wrap")}
            className={wrap.on ? "bg-surface-selected text-text" : "text-text-muted"}
            onClick={() => wrap.onChange(!wrap.on)}
          >
            <WrapText aria-hidden />
          </Button>
        ) : null}
        {absPath ? <FileButtons absPath={absPath} noEditor={noEditor} reveal={reveal} /> : null}
        {children}
      </span>
    </div>
  );
}

/** "● Unsaved changes" / "● Not saved": the toolbar's word for a draft. */
export function DraftStatus({ notSaved }: { notSaved?: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={
        notSaved
          ? "mr-1 inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-danger"
          : "mr-1 inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-warning"
      }
    >
      <span
        aria-hidden
        className={
          notSaved ? "size-1.5 rounded-full bg-danger" : "size-1.5 rounded-full bg-warning"
        }
      />
      {notSaved ? t("files.notSaved") : t("files.unsavedChanges")}
    </span>
  );
}
