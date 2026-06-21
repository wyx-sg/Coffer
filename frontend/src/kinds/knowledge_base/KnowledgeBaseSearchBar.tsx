// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchBar.tsx
//
// Retrieval bar: ONE input + Search button. External retrieval is "one query →
// one answer" — the backend auto-selects the strategy and returns ranked
// passages (click a result to open that document). No mode picker, no grep, no
// fallback hint. State + triggers live in the page.
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import type { SearchResponse } from "./api";

interface Props {
  query: string;
  searchResult: SearchResponse | null;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  onSelectDocument: (documentId: string) => void;
}

export function KnowledgeBaseSearchBar({
  query,
  searchResult,
  error,
  isPending,
  onQueryChange,
  onSearch,
  onSelectDocument,
}: Props) {
  const { t } = useTranslation();

  return (
    <section className="space-y-3">
      <div className="flex max-w-2xl flex-wrap items-center gap-2">
        <Input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) onSearch();
          }}
          placeholder={t("knowledgeBases.detail.searchPlaceholder")}
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
    </section>
  );
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
