// src/lib/hooks/useConversationFilters.ts — the Conversations page's filters,
// kept in the URL's search params (source / agent / q) so a
// filtered list survives a reload, is a link, and follows the user from the
// list into a conversation and back. See lib/conversations/filters.
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { filtersSearch, parseFilters, type ConversationFilters } from "@/lib/conversations/filters";

export function useConversationFilters() {
  const [params, setParams] = useSearchParams();
  const key = params.toString();
  // Keyed on the string so an unrelated re-render keeps the same object.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const filters = useMemo(() => parseFilters(params), [key]);
  const search = filtersSearch(filters);
  const setFilters = useCallback(
    (next: ConversationFilters) =>
      setParams(new URLSearchParams(filtersSearch(next)), { replace: true }),
    [setParams],
  );
  return { filters, setFilters, search };
}
