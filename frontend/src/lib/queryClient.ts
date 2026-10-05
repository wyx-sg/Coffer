import { QueryClient } from "@tanstack/react-query";

import { inlineApprovalMutationCache } from "./inlineApproval";

export const queryClient = new QueryClient({
  // A save made in the desktop app approves the secret binding it waits on, on the spot.
  mutationCache: inlineApprovalMutationCache(),
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});
