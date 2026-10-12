// frontend/src/components/knowledge/KnowledgeChangeParts.tsx
//
// The pieces every Change log entry is made of (KnowledgeChangeLog): its place
// on the timeline — a hairline down the left and a dot, the accent one for a
// tidy — its heading line, and the files it touched by title, each opening
// that file at its history, folded behind "N more files" when there are many.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";
import { cn } from "@/lib/utils";

/** Files an entry lists before folding the rest behind "N more files". */
const SHOWN_FILES = 5;

/** How an entry names a file: its title, or its path in the collection. */
export type TitleOf = (path: string) => string;

export function ChangeFiles({
  documents,
  uid,
  titleOf,
}: {
  documents: { path: string; added: number; removed: number }[];
  uid: string;
  titleOf: TitleOf;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  if (documents.length === 0) return null;
  const folded = documents.length > SHOWN_FILES && !all;
  const shown = folded ? documents.slice(0, SHOWN_FILES - 1) : documents;
  return (
    <ul className="flex flex-col gap-0.5">
      {shown.map((doc) => (
        <li key={doc.path} className="flex min-w-0 items-baseline gap-2 text-xs">
          <Link
            to={collectionPath(uid, doc.path, { history: true })}
            title={pathInCollection(doc.path)}
            className="min-w-0 truncate text-text hover:underline"
          >
            {titleOf(doc.path)}
          </Link>
          <span className="shrink-0 font-mono text-text-muted">
            {t("knowledge.changeLog.lines", { added: doc.added, removed: doc.removed })}
          </span>
        </li>
      ))}
      {folded ? (
        <li>
          <button
            type="button"
            onClick={() => setAll(true)}
            className="text-xs font-label text-accent-text hover:underline"
          >
            {t("knowledge.changeLog.moreFiles", { count: documents.length - shown.length })}
          </button>
        </li>
      ) : null}
    </ul>
  );
}

/** One entry on the timeline: its dot, its heading line and what follows. */
export function ChangeEntry({
  tone = "muted",
  heading,
  meta,
  children,
}: {
  tone?: "accent" | "muted";
  heading: ReactNode;
  meta: string;
  children?: ReactNode;
}) {
  return (
    <li className="relative flex flex-col gap-1.5 pb-4 pl-5 last:pb-1">
      {/* The timeline: a hairline down the left, a dot per entry. */}
      <span aria-hidden className="absolute bottom-0 left-[3px] top-2 w-px bg-border-subtle" />
      <span
        aria-hidden
        className={cn(
          "absolute left-0 top-[7px] size-[7px] rounded-full",
          tone === "accent" ? "bg-accent" : "bg-border",
        )}
      />
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
        <span className="text-sm font-medium text-text">{heading}</span>
        <span className="truncate text-xs text-text-muted">{meta}</span>
      </div>
      {children}
    </li>
  );
}
