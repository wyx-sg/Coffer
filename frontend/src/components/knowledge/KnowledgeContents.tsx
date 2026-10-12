// frontend/src/components/knowledge/KnowledgeContents.tsx
//
// A collection's Contents (spec knowledge "Show a collection's contents by
// page type"): one card per page type — the built-in types first, in the order
// a reader starts from (overview, concept, entity, how-to, decision), then a
// type the collection's README defines, then pages with no type — each with
// its type's icon (the tree's), its count and its pages by title, a few at a
// time with "N more". Sources come last in a card of their own: the waiting
// ones first, then the current ones, the superseded ones last and muted; each
// with its state (waiting, used by N pages, skipped, superseded) and its
// summary under it. A title opens its file; its description is the tooltip.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { StatusDot } from "@/components/status/StatusDot";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut, FileSummaryOut } from "@/lib/api/knowledge";
import { useKnowledgeFiles } from "@/lib/hooks/useKnowledge";
import { compareTypes, fileIcon, isBuiltInType } from "@/lib/knowledge/pageTypes";
import { collectionPath } from "@/lib/knowledge/routes";

/** Titles a card lists before "N more". */
const SHOWN = 5;

interface Props {
  collection: CollectionOut;
}

/** Where a source stands: waiting, superseded, skipped, or how many pages use it. */
function SourceState({ file }: { file: FileSummaryOut }) {
  const { t } = useTranslation();
  const label = file.superseded_by
    ? t("knowledge.contents.superseded")
    : file.waiting
      ? t("knowledge.waiting")
      : file.skipped
        ? t("knowledge.contents.skipped")
        : t("knowledge.contents.used", { count: file.cited_count });
  return (
    <span className="flex shrink-0 items-center gap-1 text-2xs text-text-muted">
      {file.waiting && !file.superseded_by ? <StatusDot tone="warn" size={6} /> : null}
      {label}
    </span>
  );
}

/** Waiting first, then current, superseded last. */
function sourceRank(file: FileSummaryOut): number {
  return file.superseded_by ? 2 : file.waiting ? 0 : 1;
}

function ContentsCard({
  label,
  files,
  uid,
  icon: Icon,
  testId,
}: {
  label: string;
  files: FileSummaryOut[];
  uid: string;
  icon: ReturnType<typeof fileIcon>;
  testId: string;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const shown = all ? files : files.slice(0, SHOWN);
  return (
    <section
      aria-label={label}
      data-testid={testId}
      className="flex min-w-0 flex-col gap-2 rounded-lg border border-border-subtle bg-surface px-3.5 py-3"
    >
      <h3 className="flex items-center gap-2 text-sm font-medium text-text">
        <Icon className="size-4 shrink-0 text-text-subtle" aria-hidden />
        <span className="truncate">{label}</span>
        <span className="text-xs font-normal text-text-muted">{files.length}</span>
      </h3>
      <ul className="flex flex-col gap-1">
        {shown.map((file) => (
          <li key={file.path} className="flex min-w-0 flex-wrap items-center gap-x-1.5 text-sm">
            <Link
              to={collectionPath(uid, file.path)}
              title={file.description || undefined}
              className={`min-w-0 truncate hover:underline ${
                file.superseded_by ? "text-text-muted line-through" : "text-text"
              }`}
            >
              {file.title || file.path.split("/").pop()}
            </Link>
            {file.kind === "source" ? <SourceState file={file} /> : null}
            {file.kind === "source" && file.summary ? (
              <p className="w-full truncate text-xs text-text-muted" title={file.summary}>
                {file.summary}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
      {files.length > SHOWN ? (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="self-start text-xs font-label text-accent-text hover:underline"
        >
          {all
            ? t("knowledge.check.fewer")
            : t("knowledge.check.more", { count: files.length - SHOWN })}
        </button>
      ) : null}
    </section>
  );
}

export function KnowledgeContents({ collection }: Props) {
  const { t } = useTranslation();
  const files = useKnowledgeFiles(collection.uid);

  let body;
  if (files.isPending) {
    body = (
      <div className="grid grid-cols-1 gap-3 py-2 sm:grid-cols-2" aria-busy>
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  } else if (files.error) {
    body = (
      <LoadErrorRow
        title={t("knowledge.contents.failed")}
        error={files.error}
        onRetry={() => void files.refetch()}
      />
    );
  } else {
    const pages = files.data.filter((f) => f.kind === "page");
    const sources = files.data
      .filter((f) => f.kind === "source")
      .sort((a, b) => sourceRank(a) - sourceRank(b));
    const types = [...new Set(pages.map((p) => p.page_type))].sort(compareTypes);
    const typeLabel = (type: string) =>
      !type ? t("knowledge.types.none") : isBuiltInType(type) ? t(`knowledge.types.${type}`) : type;
    if (pages.length === 0 && sources.length === 0) {
      body = <p className="py-2 text-sm text-text-muted">{t("knowledge.contents.none")}</p>;
    } else {
      body = (
        <div className="grid grid-cols-1 gap-3 py-1 sm:grid-cols-2">
          {types.map((type) => (
            <ContentsCard
              key={type || "-"}
              label={typeLabel(type)}
              files={pages.filter((p) => p.page_type === type)}
              uid={collection.uid}
              icon={fileIcon({ kind: "page", page_type: type })}
              testId={`knowledge-contents-${type || "untyped"}`}
            />
          ))}
          {sources.length > 0 ? (
            <ContentsCard
              label={t("knowledge.tree.sources")}
              files={sources}
              uid={collection.uid}
              icon={fileIcon({ kind: "source", page_type: "" })}
              testId="knowledge-contents-sources"
            />
          ) : null}
        </div>
      );
    }
  }

  return (
    <SettingsSection
      title={t("knowledge.contents.title")}
      description={t("knowledge.contents.description")}
      testId="knowledge-contents"
    >
      {body}
    </SettingsSection>
  );
}
