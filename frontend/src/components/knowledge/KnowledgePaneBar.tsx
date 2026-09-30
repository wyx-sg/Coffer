// frontend/src/components/knowledge/KnowledgePaneBar.tsx
//
// The 48px bar over every Knowledge pane view (boards 5.1.01, 5.1.09, 5.1.10,
// 5.1.13): where you are — the collection, its folders and the open file in
// the mono face, or "Recent changes › Curation pass" — then the view's tabs,
// if it has any, and its actions pushed right. One component so a document, an
// item, a collection and a pass all say where they are the same way.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  /** Where the crumb leads; the last crumb is where you are and leads nowhere. */
  to?: string;
  /** A file-system name (collection, folder, file) — drawn in the mono face. */
  mono?: boolean;
}

interface Props {
  crumbs: Crumb[];
  /** Beside the crumbs: a view's tabs. */
  tabs?: ReactNode;
  actions?: ReactNode;
}

export function KnowledgePaneBar({ crumbs, tabs, actions }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-border-subtle px-6">
      <nav
        aria-label={t("knowledge.document.where")}
        className="flex min-w-0 items-center gap-1 overflow-hidden whitespace-nowrap"
      >
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          const cls = cn(
            "truncate",
            c.mono ? "font-mono text-xs" : "text-sm",
            last ? "text-text" : "text-text-muted hover:text-text",
          );
          return (
            <span key={`${i}-${c.label}`} className="flex min-w-0 items-center gap-1">
              {i > 0 ? (
                <ChevronRight className="size-3 shrink-0 text-text-subtle" aria-hidden />
              ) : null}
              {c.to && !last ? (
                <Link to={c.to} className={cls}>
                  {c.label}
                </Link>
              ) : (
                <span className={cls} aria-current={last ? "location" : undefined}>
                  {c.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>
      {tabs}
      {actions ? (
        <span className="ml-auto flex shrink-0 items-center gap-1.5">{actions}</span>
      ) : null}
    </div>
  );
}

/** A tab link in the bar: 48px tall, the current one underlined in ink. */
export function PaneBarTab({
  to,
  current,
  children,
  onMouseDown,
}: {
  to: string;
  current: boolean;
  children: ReactNode;
  onMouseDown?: () => void;
}) {
  return (
    <Link
      to={to}
      onMouseDown={onMouseDown}
      aria-current={current ? "page" : undefined}
      className={cn(
        "inline-flex h-12 items-center gap-1.5 px-0.5 text-sm transition-colors",
        current
          ? "font-label text-text shadow-[inset_0_-2px_0_rgb(var(--text))]"
          : "font-book text-text-muted hover:text-text",
      )}
    >
      {children}
    </Link>
  );
}
