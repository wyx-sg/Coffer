// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchPanel.tsx
//
// Relevance search section (keyword / vector) with a mode toggle, query box,
// and the rendered passages. State and the search trigger live in the page.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { translateApiError } from "@/lib/api/errors";
import { type RetrievalMode, type SearchResponse } from "./api";

interface Props {
  query: string;
  mode: RetrievalMode;
  result: SearchResponse | null;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onModeChange: (mode: RetrievalMode) => void;
  onSearch: () => void;
}

export function KnowledgeBaseSearchPanel({
  query,
  mode,
  result,
  error,
  isPending,
  onQueryChange,
  onModeChange,
  onSearch,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{t("knowledgeBases.detail.search")}</h2>
      <div className="flex flex-wrap gap-2">
        <select
          aria-label={t("knowledgeBases.detail.mode")}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={mode}
          onChange={(e) => onModeChange(e.target.value as RetrievalMode)}
        >
          <option value="keyword">{t("knowledgeBases.modes.keyword")}</option>
          <option value="vector">{t("knowledgeBases.modes.vector")}</option>
        </select>
        <Input
          className="flex-1"
          placeholder={t("knowledgeBases.detail.searchPlaceholder")}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && query.trim()) onSearch();
          }}
        />
        <Button onClick={onSearch} disabled={!query.trim() || isPending}>
          {t("knowledgeBases.detail.search")}
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{translateApiError(t, error)}</p> : null}
      {result ? (
        <div className="space-y-2">
          {result.fallback ? (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              {t("knowledgeBases.detail.fallback", { mode: result.fallback })}
            </p>
          ) : null}
          {result.passages.length > 0 ? (
            <ul className="space-y-2 text-sm">
              {result.passages.map((p, i) => (
                <li key={`${p.document_id}:${p.position}`} className="rounded border p-2">
                  <div className="font-medium">
                    {i + 1}. {p.title}{" "}
                    <span className="text-xs text-muted-foreground">
                      {t("knowledgeBases.detail.score", { score: p.score.toFixed(3) })}
                    </span>
                  </div>
                  <div className="line-clamp-3 text-muted-foreground">{p.text}</div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">{t("knowledgeBases.detail.noMatches")}</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
