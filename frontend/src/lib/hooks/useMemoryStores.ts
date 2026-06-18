// frontend/src/lib/hooks/useMemoryStores.ts
//
// TanStack Query binding for the list of memory stores (spec 007). The memory
// page and the agent Memory tab both read this, caching the store ARRAY under
// ["memory-stores"]; they must not register a second query under that key with
// a different shape (that collision crashed the tab).
import { useQuery } from "@tanstack/react-query";

import { listMemoryStores } from "@/kinds/memory/api";

export function useMemoryStores() {
  return useQuery({
    queryKey: ["memory-stores"],
    queryFn: async () => (await listMemoryStores()).memory_stores,
  });
}
