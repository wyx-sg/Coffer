// frontend/src/components/knowledge/KnowledgeFileLine.tsx
//
// The one quiet line under an open file's title (spec knowledge "Show a
// collection as one tree of read-only documents in the web UI"), read from the
// file's frontmatter and the daemon's resolution of it; a part with no data is
// left out. A page: its type, when it was created and by whom, and its sources
// — each opening that source, one that names no source struck through. A
// source: when it was created and by whom, the pages that cite it (each
// opening the page) or the Waiting mark.
// Any other file: when it was created and by whom.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { StatusPill } from "@/components/status/StatusPill";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { FileOut } from "@/lib/api/knowledge";
import { agentLabel } from "@/lib/knowledge/changes";
import { collectionPath } from "@/lib/knowledge/routes";

interface Props {
  file: FileOut;
  collectionUid: string;
}

const LINK = "text-text underline decoration-border underline-offset-2 hover:decoration-text";

/** Comma-separated parts, each its own element. */
function Joined({ children }: { children: ReactNode[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1">
      {children.map((child, i) => (
        <span key={i}>
          {child}
          {i < children.length - 1 ? "," : null}
        </span>
      ))}
    </span>
  );
}

export function KnowledgeFileLine({ file, collectionUid }: Props) {
  const { t, i18n } = useTranslation();
  const parts: ReactNode[] = [];

  if (file.kind === "page" && file.page_type) {
    parts.push(
      <span
        key="type"
        data-testid="page-type"
        className="rounded-sm bg-chip px-1.5 py-px font-mono text-2xs text-text"
      >
        {file.page_type}
      </span>,
    );
  }

  // Created: the frontmatter's `created_at` and `actor` — nothing else records it.
  if (file.created_at && !Number.isNaN(Date.parse(file.created_at))) {
    const date = new Date(file.created_at).toLocaleDateString(i18n.language, {
      month: "short",
      day: "numeric",
    });
    const who = agentLabel(t, file.actor);
    parts.push(
      <span key="created">
        {t("knowledge.document.createdBy", {
          date,
          who: who === t("knowledge.writer.user") ? t("knowledge.document.you") : who,
        })}
      </span>,
    );
  }

  if (file.kind === "page" && file.sources.length > 0) {
    parts.push(
      <span key="sources" className="inline-flex flex-wrap items-center gap-x-1">
        {t("knowledge.document.sources")}
        <Joined>
          {file.sources.map((source) =>
            source.path ? (
              <Link
                key={source.slug}
                to={collectionPath(collectionUid, source.path)}
                className={LINK}
              >
                {source.title || source.slug}
              </Link>
            ) : (
              <Tooltip key={source.slug}>
                <TooltipTrigger asChild>
                  <s tabIndex={0} className="cursor-help text-text-subtle">
                    {source.slug}
                  </s>
                </TooltipTrigger>
                <TooltipContent>
                  {t("knowledge.document.missingSource", { slug: source.slug })}
                </TooltipContent>
              </Tooltip>
            ),
          )}
        </Joined>
      </span>,
    );
  }

  if (file.kind === "source" && file.waiting) {
    parts.push(
      <StatusPill key="waiting" tone="warn">
        {t("knowledge.waiting")}
      </StatusPill>,
    );
  } else if (file.kind === "source" && file.cited_by.length > 0) {
    parts.push(
      <span key="cited" className="inline-flex flex-wrap items-center gap-x-1">
        {t("knowledge.document.citedBy", { count: file.cited_by.length })}
        <Joined>
          {file.cited_by.map((page) => (
            <Link key={page.path} to={collectionPath(collectionUid, page.path)} className={LINK}>
              {page.title || page.path.split("/").pop()}
            </Link>
          ))}
        </Joined>
      </span>,
    );
  }

  return (
    <p
      data-testid="file-line"
      className="mb-5 mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-muted"
    >
      {parts.map((part, i) => (
        <span key={i} className="inline-flex items-center gap-x-2">
          {i > 0 ? <span aria-hidden>·</span> : null}
          {part}
        </span>
      ))}
    </p>
  );
}
