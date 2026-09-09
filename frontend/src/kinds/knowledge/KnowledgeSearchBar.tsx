// frontend/src/kinds/knowledge/KnowledgeSearchBar.tsx
//
// The one retrieval bar for a knowledge scope: a shared SearchInput (magnifier
// + clear ×) plus an action button. Both lanes use it — Entries calls it
// "Recall", Documents calls it "Search" — because the mechanic is identical:
// external retrieval is "one query → one answer", the backend auto-selects the
// strategy, running it filters the lane's list to the matches and opens the top
// hit highlighted, and clearing the box returns to the full list. State +
// triggers live in the lane.
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
  /** Lane-specific placeholder ("Recall entries…" / "Search documents…"). */
  placeholder: string;
  /** Lane-specific action label ("Recall" / "Search"); also the input's aria-label. */
  actionLabel: string;
}

export function KnowledgeSearchBar({
  query,
  error,
  isPending,
  onQueryChange,
  onSearch,
  placeholder,
  actionLabel,
}: Props) {
  const { t } = useTranslation();

  return (
    <section className="space-y-2">
      <div className="flex max-w-2xl flex-wrap items-center gap-2">
        <SearchInput
          className="min-w-[16rem] flex-1"
          value={query}
          onChange={onQueryChange}
          onSearch={onSearch}
          placeholder={placeholder}
          ariaLabel={actionLabel}
        />
        <Button onClick={onSearch} disabled={isPending || !query.trim()}>
          <Search className="mr-1.5 size-3.5" /> {actionLabel}
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
