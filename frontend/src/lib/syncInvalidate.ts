// src/lib/syncInvalidate.ts — "something about Sync changed": re-read it, the rounds list from its head only.
//
// Sync's rounds list grows by cursor as it is read (`useSyncRuns`). Left to
// `invalidateQueries`, every page already loaded would be fetched again, one
// after the other, for what is at most one new round at the head. So the loaded
// pages are cut back to the first before the refetch: a new round shows on top,
// and the older ones are read again only if the reader scrolls to them.
import type { InfiniteData, QueryClient } from "@tanstack/react-query";

import { syncKey, syncRunsKey } from "@/lib/api/queryKeys";

export function invalidateSync(qc: QueryClient): void {
  qc.setQueryData<InfiniteData<unknown, unknown>>(syncRunsKey, (data) =>
    data && data.pages.length > 1
      ? { pages: data.pages.slice(0, 1), pageParams: data.pageParams.slice(0, 1) }
      : data,
  );
  void qc.invalidateQueries({ queryKey: syncKey });
}
