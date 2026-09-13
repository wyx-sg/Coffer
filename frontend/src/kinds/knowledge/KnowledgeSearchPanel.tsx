// frontend/src/kinds/knowledge/KnowledgeSearchPanel.tsx
//
// Ranked (or literal-fallback) search over the collection in view (spec
// knowledge FR-024, web surface FR-060/FR-061). The filter box above the tree
// is a client-side name match; this is the other thing — a meaning-based
// query answered by the backend, which always says HOW it answered
// (`mode`) so a degraded literal answer can never be mistaken for a ranked
// one (FR-082). An empty result set gets its own quiet message, not an error.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { SearchOut } from "./types";
import { useKnowledgeSearch } from "./useKnowledge";

/**
 * `SearchService.search` (backend) reports its fallback reason as one of a
 * few fixed English phrases, not an error code — map the ones known today to
 * localized copy and fall through to the raw phrase for anything newer.
 */
const REASON_I18N_KEY: Record<string, string> = {
  "no internal connection": "knowledge.search.reasonText.noConnection",
  "embedding unavailable": "knowledge.search.reasonText.embeddingUnavailable",
  "nothing ranked above threshold": "knowledge.search.reasonText.noneAboveThreshold",
};

interface Props {
  /** Restricts the query to this collection. */
  collection: string;
  /** Fired when a result is chosen, so the caller can open it in the preview. */
  onSelectPath: (path: string) => void;
}

export function KnowledgeSearchPanel({ collection, onSelectPath }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const search = useKnowledgeSearch();
  const result: SearchOut | undefined = search.data;

  const submit = () => {
    const q = query.trim();
    if (!q) return;
    search.mutate({ query: q, collection });
  };

  const reasonText = result?.reason
    ? (REASON_I18N_KEY[result.reason] ? t(REASON_I18N_KEY[result.reason]) : result.reason)
    : "";

  return (
    <div className="space-y-2 rounded-md border p-2">
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("knowledge.search.placeholder")}
          aria-label={t("knowledge.search.placeholder")}
        />
        <Button
          type="submit"
          size="sm"
          variant="outline"
          disabled={search.isPending || !query.trim()}
        >
          <Search className="mr-1.5 size-3.5" />
          {t("knowledge.search.button")}
        </Button>
      </form>

      {search.isPending ? (
        <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : result ? (
        <div className="space-y-2">
          {result.mode === "literal" ? (
            <p className="rounded-sm bg-muted px-2 py-1 text-xs text-muted-foreground">
              {t("knowledge.search.literalNotice", { reason: reasonText })}
            </p>
          ) : null}

          {result.results.length === 0 ? (
            <p className="px-1 text-sm text-muted-foreground">{t("knowledge.search.noResults")}</p>
          ) : (
            <ul className="space-y-1.5">
              {result.results.map((hit) => (
                <li key={hit.path}>
                  <button
                    type="button"
                    onClick={() => onSelectPath(hit.path)}
                    className="block w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-secondary hover:text-foreground"
                  >
                    <span className="block truncate font-medium">{hit.title}</span>
                    {hit.description ? (
                      <span className="block truncate text-xs text-muted-foreground">
                        {hit.description}
                      </span>
                    ) : null}
                    <span className="block truncate text-xs text-muted-foreground/80">
                      {hit.path}
                    </span>
                    {hit.lines.length > 0 ? (
                      <span className="mt-0.5 block space-y-0.5 font-mono text-xs text-muted-foreground">
                        {hit.lines.map((line) => (
                          <span key={line.line_number} className="block truncate">
                            {line.line_number}: {line.line}
                          </span>
                        ))}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
