// frontend/src/kinds/memory/MemorySingleDocLane.tsx
//
// Shared read-only single-document lane for the memory store detail page: a
// header (title + FileActions) over the unified Markdown preview. Used by the
// Rules and Changelog lanes — both are one curated doc with a friendly
// empty-state when the store has none. Never a hand-styled <pre>: the body
// always flows through <FindableMarkdown>.
import { translateApiError } from "@/lib/api/errors";
import { useTranslation } from "react-i18next";

import { FileActions } from "@/components/FileActions";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";

interface Props {
  title: string;
  /** Markdown body; null/empty renders the empty-state. */
  text: string | null | undefined;
  /** Absolute on-disk path for FileActions (open/reveal/copy). */
  path?: string;
  isLoading: boolean;
  error?: unknown;
  /** Shown when the doc is absent. */
  emptyLabel: string;
}

export function MemorySingleDocLane({ title, text, path, isLoading, error, emptyLabel }: Props) {
  const { t } = useTranslation();

  if (isLoading) {
    return <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>;
  }
  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }
  if (!text) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center rounded-md border border-dashed border-border">
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <span className="truncate font-medium">{title}</span>
        {path ? <FileActions filePath={path} /> : null}
      </div>
      <FindableMarkdown className="max-h-[60vh] overflow-auto p-4">{text}</FindableMarkdown>
    </div>
  );
}
