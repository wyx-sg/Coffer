// frontend/src/lib/hooks/useKnowledgeScopes.ts
//
// TanStack Query binding for the list of knowledge scopes. The Knowledge page
// and the agent Knowledge tab both read this, caching the scope ARRAY under
// ["knowledge-scopes"]; they must not register a second query under that key
// with a different shape (that collision crashed the tab).
import { useQuery } from "@tanstack/react-query";

import { listScopes } from "@/kinds/knowledge/api";

export function useKnowledgeScopes() {
  return useQuery({
    queryKey: ["knowledge-scopes"],
    queryFn: async () => (await listScopes()).scopes,
  });
}
