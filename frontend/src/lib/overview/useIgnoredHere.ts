// src/lib/overview/useIgnoredHere.ts — the items ignored on Overview that belong to the page on screen.
//
// An ignored item leaves Overview, so its own page is where it can come back
// (spec web-ui "Let the user ignore any item on Overview"): an item belongs to
// the page its Overview name links to (`itemPage`), matched against the
// current pathname (and tab query for Activity). Every part that is missing —
// no router, no query client, no data yet — yields none.
import { useInRouterContext, useLocation } from "react-router-dom";
import { QueryClientContext, useQuery } from "@tanstack/react-query";
import { useContext } from "react";

import { agentsApi } from "@/lib/api/agents";
import { agentsKey } from "@/lib/api/queryKeys";
import { useAttention, type AttentionItem } from "@/lib/hooks/useAttention";
import { itemPage } from "./attention";

/** Whether the tree has a router and a query client to read from. */
export function useCanReadIgnored(): boolean {
  const inRouter = useInRouterContext();
  const client = useContext(QueryClientContext);
  return inRouter && client !== undefined;
}

/** Ignored items whose page is the current one. Mount only where
 *  `useCanReadIgnored()` holds. */
export function useIgnoredHere(): AttentionItem[] {
  const { pathname, search } = useLocation();
  const attention = useAttention();
  const ignored = attention.data?.ignored ?? [];
  // An agent's page is addressed by its type, so the agents are read only
  // when an ignored item is about one.
  const agents = useQuery({
    queryKey: agentsKey,
    queryFn: async () => (await agentsApi.list()).items,
    enabled: ignored.some((item) => item.kind === "agent"),
  });
  const here = `${pathname}${search}`;
  return ignored.filter((item) => {
    const agentType =
      item.kind === "agent" ? agents.data?.find((a) => a.uid === item.uid)?.type : undefined;
    const page = itemPage(item, agentType);
    return page === here || page === pathname;
  });
}
