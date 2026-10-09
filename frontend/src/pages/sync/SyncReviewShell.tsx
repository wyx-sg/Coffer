// frontend/src/pages/sync/SyncReviewShell.tsx
//
// The one shape every Sync review page shares (spec vault-sync "Review a
// file's change before acting on it"): changes to push, held deletions,
// conflicts and a join's differing files. Files down the left, each with a
// mark and one line of state; the chosen file on the right; the page's
// actions in a footer under both. The Status tab lists no files itself — its
// banner opens the page, and the person reads each file here before acting.
import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { LineCounts } from "@/components/change-preview/LineCounts";
import type { RoundFileDiff, SyncChange } from "@/lib/api/sync";
import { cn } from "@/lib/utils";
import { ChangeMark } from "./SyncChangeMark";
import { SyncFileDiffBody } from "./SyncFileDiffBody";

export function SyncReviewShell({
  nav,
  footer,
  children,
}: {
  nav: ReactNode;
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
      <div className="flex h-[clamp(420px,70vh,720px)]">
        {nav}
        <div className="flex min-w-0 flex-1 overflow-y-auto">{children}</div>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-border bg-surface-footer px-5 py-3">
        {footer}
      </div>
    </div>
  );
}

export interface ReviewNavItem {
  path: string;
  /** The mark before the path: a change mark, a check, a red dot. */
  mark: ReactNode;
  /** One line under the path: who wrote it, what its answer is. */
  note: ReactNode;
  testId?: string;
}

export function SyncReviewNav({
  items,
  selected,
  onSelect,
}: {
  items: ReviewNavItem[];
  selected: string;
  onSelect: (path: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <nav
      aria-label={t("sync.resolve.filesLabel")}
      className="flex w-[300px] shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-border bg-surface-sidebar px-2 py-3"
    >
      <p className="px-2.5 pb-1 text-2xs font-semibold uppercase tracking-[.02em] text-text-muted">
        {t("sync.resolve.files")}
      </p>
      {items.map((item) => {
        const current = item.path === selected;
        return (
          <button
            key={item.path}
            type="button"
            aria-current={current || undefined}
            onClick={() => onSelect(item.path)}
            data-testid={item.testId}
            className={cn(
              "flex items-start gap-2 rounded-item px-2.5 py-2 text-left transition-colors duration-fast",
              current ? "bg-surface-selected" : "hover:bg-surface-hover",
            )}
          >
            <span className="inline-flex pt-0.5">{item.mark}</span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="truncate font-mono text-xs text-text">{item.path}</span>
              <span className="text-xs text-text-muted">{item.note}</span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

/** The right pane of a read-only review: the file, its +N −M, its diff. */
export function SyncReviewDiffPane({
  path,
  status,
  note,
  query,
}: {
  path: string;
  status: SyncChange["status"];
  note: ReactNode;
  query: UseQueryResult<RoundFileDiff>;
}) {
  const counts = query.data?.kind === "text" ? query.data : null;
  return (
    <section
      aria-label={path}
      className="flex min-w-0 flex-1 flex-col gap-4 px-7 py-5"
      data-testid="sync-review-pane"
    >
      <div className="flex items-start gap-2.5">
        <span className="pt-0.5">
          <ChangeMark status={status} />
        </span>
        <div className="flex min-w-0 flex-col gap-[3px]">
          <span className="truncate font-mono text-sm font-medium text-text">{path}</span>
          <span className="text-xs text-text-muted">{note}</span>
        </div>
        {counts ? (
          <span className="ml-auto shrink-0">
            <LineCounts added={counts.added} removed={counts.removed} />
          </span>
        ) : null}
      </div>
      <SyncFileDiffBody query={query} testId="sync-review-diff" />
    </section>
  );
}
