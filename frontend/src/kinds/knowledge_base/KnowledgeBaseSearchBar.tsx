// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchBar.tsx
//
// Unified retrieval bar: ONE input with a mode dropdown (keyword / vector /
// grep) — replacing the separate Search and Grep sections. keyword/vector
// return ranked passages (click a result to open that document); grep returns
// raw line hits over the Markdown files. State + triggers live in the page.
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import type { GrepResponse, RetrievalMode, SearchResponse } from "./api";

interface Props {
  query: string;
  mode: RetrievalMode;
  searchResult: SearchResponse | null;
  grepResult: GrepResponse | null;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onModeChange: (mode: RetrievalMode) => void;
  onSearch: () => void;
  onSelectDocument: (documentId: string) => void;
}

const MODES: RetrievalMode[] = ["keyword", "vector", "grep"];

export function KnowledgeBaseSearchBar({
  query,
  mode,
  searchResult,
  grepResult,
  error,
  isPending,
  onQueryChange,
  onModeChange,
  onSearch,
  onSelectDocument,
}: Props) {
  const { t } = useTranslation();

  return (
    <section className="space-y-3">
      <div className="flex max-w-2xl flex-wrap items-center gap-2">
        <Select value={mode} onValueChange={(v) => onModeChange(v as RetrievalMode)}>
          <SelectTrigger className="w-32" aria-label={t("knowledgeBases.detail.mode")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MODES.map((m) => (
              <SelectItem key={m} value={m}>
                {t(`knowledgeBases.modes.${m}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) onSearch();
          }}
          placeholder={
            mode === "grep"
              ? t("knowledgeBases.detail.grepPlaceholder")
              : t("knowledgeBases.detail.searchPlaceholder")
          }
          className="min-w-[16rem] flex-1"
        />
        <Button onClick={onSearch} disabled={isPending || !query.trim()}>
          <Search className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.search")}
        </Button>
      </div>

      {error ? (
        <p className="text-sm text-destructive" role="alert">
          {translateApiError(t, error)}
        </p>
      ) : null}

      {searchResult ? (
        <SearchResults result={searchResult} onSelectDocument={onSelectDocument} />
      ) : null}
      {grepResult ? (
        <GrepResults result={grepResult} onSelectDocument={onSelectDocument} />
      ) : null}
    </section>
  );
}

// Backend doc paths are always `docs/<doc-id>.md` (see pipeline_helpers.py).
// Derive the doc id so a grep hit can open its document. Returns null for any
// path that does not match `docs/<non-empty>.md` so we never emit a broken or
// empty-id click; such hits render as plain (non-clickable) text instead.
function docIdFromGrepPath(path: string): string | null {
  const match = /^docs\/(.+)\.md$/.exec(path);
  const docId = match?.[1];
  return docId ? docId : null;
}

function SearchResults({
  result,
  onSelectDocument,
}: {
  result: SearchResponse;
  onSelectDocument: (documentId: string) => void;
}) {
  const { t } = useTranslation();
  if (result.passages.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("knowledgeBases.detail.noMatches")}</p>;
  }
  return (
    <div className="space-y-1.5">
      {result.fallback ? (
        <p className="text-xs text-muted-foreground">
          {t("knowledgeBases.detail.fallback", { mode: result.fallback })}
        </p>
      ) : null}
      <ul className="divide-y divide-border rounded-md border border-border">
        {result.passages.map((p, i) => (
          <li key={`${p.document_id}-${i}`}>
            <button
              type="button"
              onClick={() => onSelectDocument(p.document_id)}
              className="block w-full px-3 py-2 text-left hover:bg-secondary"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{p.title}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {t("knowledgeBases.detail.score", { score: p.score.toFixed(3) })}
                </span>
              </div>
              <p className="line-clamp-2 text-xs text-muted-foreground">{p.text}</p>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function GrepResults({
  result,
  onSelectDocument,
}: {
  result: GrepResponse;
  onSelectDocument: (documentId: string) => void;
}) {
  const { t } = useTranslation();
  if (result.hits.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("knowledgeBases.detail.noMatches")}</p>;
  }
  return (
    <div className="space-y-1.5">
      {result.truncated ? (
        <p className="text-xs text-muted-foreground">{t("knowledgeBases.detail.truncated")}</p>
      ) : null}
      <ul className="divide-y divide-border rounded-md border border-border font-mono text-xs">
        {result.hits.map((h, i) => {
          const docId = docIdFromGrepPath(h.path);
          const row = (
            <>
              <span className="shrink-0 text-muted-foreground">{h.line_number}</span>
              <span className="truncate">{h.line}</span>
            </>
          );
          return (
            <li key={i}>
              {docId ? (
                <button
                  type="button"
                  onClick={() => onSelectDocument(docId)}
                  className="flex w-full gap-2 px-3 py-1.5 text-left hover:bg-secondary"
                >
                  {row}
                </button>
              ) : (
                <div className="flex gap-2 px-3 py-1.5">{row}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
