// frontend/src/kinds/memory/MemoryRecallPanel.tsx
//
// Recall section: a SearchInput (magnifier + clear ×) plus a Recall button.
// External retrieval is "one query → one answer" — the backend auto-selects the
// strategy. Running a recall filters the fact tree to the hits and opens the top
// match highlighted in the viewer (both handled by the page); clearing the box
// returns to the full list. State + trigger live in the page.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { SearchInput } from "@/components/SearchInput";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  query: string;
  error: unknown;
  isPending: boolean;
  onQueryChange: (value: string) => void;
  onRecall: () => void;
}

export function MemoryRecallPanel({ query, error, isPending, onQueryChange, onRecall }: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-2">
      <div className="flex max-w-2xl flex-wrap items-center gap-2">
        <SearchInput
          className="flex-1"
          value={query}
          onChange={onQueryChange}
          onSearch={onRecall}
          placeholder={t("memory.detail.recallPlaceholder")}
          ariaLabel={t("memory.detail.recall")}
        />
        <Button onClick={onRecall} disabled={!query.trim() || isPending}>
          {t("memory.detail.recall")}
        </Button>
      </div>
      {error ? <p className="text-sm text-destructive">{translateApiError(t, error)}</p> : null}
    </section>
  );
}
