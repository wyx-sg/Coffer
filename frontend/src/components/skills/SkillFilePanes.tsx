// frontend/src/components/skills/SkillFilePanes.tsx
// The pieces of the Files tab's reader that a managed skill's viewer
// (SkillFileViewer) and the read-only one (ReadOnlyFileView) share (canvas
// 4.3.01, 4.3.12–4.3.16, Foundations 0.6.03): the 40px toolbar — the path in
// mono, the size, the actions at the right — the "Can't preview binary file"
// state, the 32px grey bar over a file too large to read whole, and the body:
// rendered Markdown (its front matter a key / value block above the title) or
// the code view with line numbers and an optional wrap.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, WrapText } from "lucide-react";

import { CodeView } from "@/components/preview/CodeView";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { SkillSegmented } from "@/components/skills/SkillSegmented";
import { isMarkdown, type FileView } from "@/components/skills/skillFileHelpers";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";

/** The toolbar over a file: its path (under the skill's name) and size, then the actions. */
export function FileBar({
  path,
  size,
  status,
  children,
}: {
  path: string;
  size?: number;
  /** "Unsaved changes ⌘S" / "Not saved", between the size and the actions. */
  status?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border-subtle px-3">
      <span className="min-w-0 truncate font-mono text-xs text-text-muted">{path}</span>
      {size === undefined ? null : (
        <span className="shrink-0 text-xs text-text-subtle">{formatBytes(size)}</span>
      )}
      {status}
      <span className="ml-auto flex shrink-0 items-center gap-1.5">{children}</span>
    </div>
  );
}

export function WrapToggle({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  const { t } = useTranslation();
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-pressed={on}
      aria-label={t("skills.files.wrap")}
      title={t("skills.files.wrap")}
      className={on ? "bg-surface-selected text-text" : "text-text-muted"}
      onClick={() => onChange(!on)}
    >
      <WrapText aria-hidden />
    </Button>
  );
}

export function ViewSwitch({
  value,
  onChange,
}: {
  value: FileView;
  onChange: (view: FileView) => void;
}) {
  const { t } = useTranslation();
  return (
    <SkillSegmented
      label={t("skills.files.viewLabel")}
      value={value}
      onChange={onChange}
      options={[
        { value: "preview", label: t("skills.files.preview") },
        { value: "source", label: t("skills.files.source") },
      ]}
    />
  );
}

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
      <p className="text-sm font-label text-text">{t("skills.files.binaryTitle")}</p>
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
      {t("skills.files.truncatedBar", { shown: formatBytes(shown), total: formatBytes(total) })}
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

/** The file itself: rendered Markdown, or its text with line numbers. */
export function FileBody({
  path,
  text,
  view,
  wrap,
  truncated,
}: {
  path: string;
  text: string;
  view: FileView;
  wrap: boolean;
  truncated: boolean;
}) {
  const rendered = isMarkdown(path) && !truncated && view === "preview";
  return (
    <div className="flex min-h-0 flex-1 flex-col p-3">
      {rendered ? (
        <FindableMarkdown fill className="px-3 pt-1">
          {text}
        </FindableMarkdown>
      ) : (
        <CodeView value={text} filename={path} fill wrap={wrap} />
      )}
    </div>
  );
}
