// frontend/src/lib/hooks/useKeychain.ts — TanStack Query mutations for storing
// and clearing OS-keychain secrets (spec 008, Settings → AI). Secrets are
// write-only, so there is no query — only set/remove mutations.
import { useMutation } from "@tanstack/react-query";

import { keychainApi } from "@/lib/api/keychain";

export function useSetKeychainSecret() {
  return useMutation({
    mutationFn: (vars: { ref: string; value: string }) => keychainApi.set(vars.ref, vars.value),
  });
}

export function useRemoveKeychainSecret() {
  return useMutation({
    mutationFn: (ref: string) => keychainApi.remove(ref),
  });
}
