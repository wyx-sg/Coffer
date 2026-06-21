// frontend/src/kinds/knowledge_base/KnowledgeBaseSearchBar.tsx
//
// Retrieval bar: a shared SearchInput (magnifier + clear ×) + Search button.
// External retrieval is "one query → one answer" — the backend auto-selects the
// strategy. Running a search filters the document tree to the matched documents
// and opens the top hit highlighted in the viewer (both handled by the page);
// clearing the box returns to the full list. State + triggers live in the page.
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/SearchInput";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  query: string;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
}

export function KnowledgeBaseSearchBar({
  query,
  error,
  isPending,
  onQueryChange,
  onSearch,
}: Props) {
  const { t } = useTranslation();

  return (
    <section className="space-y-3">
      <div className="flex max-w-2xl flex-wrap items-center gap-2">
        <SearchInput
          className="min-w-[16rem] flex-1"
          value={query}
          onChange={onQueryChange}
          onSearch={onSearch}
          placeholder={t("knowledgeBases.detail.searchPlaceholder")}
          ariaLabel={t("knowledgeBases.detail.search")}
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
    </section>
  );
}
