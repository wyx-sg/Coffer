// frontend/src/lib/hooks/useProviders.ts — TanStack Query bindings for providers.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  providersApi,
  type ProviderCreate,
  type ProviderPatch,
  type Protocol,
} from "@/lib/api/providers";
import { useToast } from "@/components/ui/toast";
import { providerKey, providersKey } from "@/lib/api/queryKeys";

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useProviderToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

export function useProviders() {
  return useQuery({
    queryKey: providersKey,
    queryFn: async () => (await providersApi.list()).providers,
  });
}

/** One connection, for its detail page. The key extends providersKey so the
 *  list-level invalidation every mutation already does refreshes it too. */
export function useProvider(uid: string) {
  return useQuery({
    queryKey: providerKey(uid),
    queryFn: () => providersApi.get(uid),
    enabled: uid !== "",
  });
}

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderCreate) => providersApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (vars: { uid: string; patch: ProviderPatch }) =>
      providersApi.update(vars.uid, vars.patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
    onError,
  });
}

// There is no `useRenameProvider`. Renaming a connection is `useRenameResource`
// (`lib/hooks/useResourceMutations.ts`), the same PATCH every kind renames
// through — and it is a plain cache INVALIDATION, not a removal: the old key
// was `providerKey(name)` and had to be evicted because nothing answered there
// afterwards, while `providerKey(uid)` answers the same row before and after.
// The detail page's URL does not change either, so nothing navigates.

export function useDeleteProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (uid: string) => providersApi.remove(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
    onError,
  });
}

export function useActivateProvider() {
  const qc = useQueryClient();
  // Switching writes native config; a failure (e.g. unwritable config dir)
  // must surface rather than silently leave the old provider active.
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (uid: string) => providersApi.activate(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
    onError,
  });
}

/** Switch a wire's agent(s) back to their own built-in login (clears the active
 * connection + removes Coffer's projection). */
export function useUseBuiltinProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (wire: Protocol) => providersApi.useBuiltin(wire),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
    onError,
  });
}

/** Set which connection Coffer's internal engine uses (≤1 globally). */
export function useSetInternalDefaultProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (uid: string) => providersApi.setInternalDefault(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
    onError,
  });
}

/** Set which connection Coffer transcribes speech on (≤1 globally).
 *
 *  Its own mutation rather than a flag on the one above, because the two flags
 *  are independent: transcription runs on a different endpoint from chat and
 *  neither falls back to the other. */
export function useSetTranscribeDefaultProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (uid: string) => providersApi.setTranscribeDefault(uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
    },
    onError,
  });
}
