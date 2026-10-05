// src/components/secret/useShownCiter.ts — a citer as the Secrets page shows it, with custom-tool groups told
// apart from MCP servers (both are `mcp_server` on the wire).
import { useMemo } from "react";

import { useCustomToolGroups } from "@/lib/hooks/useCustomTools";
import { shownCiter, type Citer } from "./secretRows";

export function useShownCiter(): (citer: Citer) => Citer {
  const { data } = useCustomToolGroups();
  const groups = useMemo(() => new Set((data ?? []).map((g) => g.name)), [data]);
  return (citer) => shownCiter(citer, groups);
}
