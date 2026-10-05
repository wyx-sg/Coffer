// frontend/src/lib/hooks/useProviders.ts — TanStack Query bindings for providers.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import {
  providersApi,
  type Provider,
  type ProviderCreate,
  type ProviderPatch,
} from "@/lib/api/providers";
import { useToast } from "@/components/ui/toast";
import {
  endpointModelsKey,
  localRuntimesKey,
  pendingApprovalsKey,
  providerKey,
  providersKey,
  secretsListKey,
} from "@/lib/api/queryKeys";

/** Shared onError → toast handler — a failed mutation must never be silent. */
function useProviderToastError() {
  const { t } = useTranslation();
  const { toast } = useToast();
  return (error: unknown) => toast.error(translateApiError(t, error));
}

/** The connections. `enabled` is false while the Models feature is off: a
 *  surface that is always on reads them only when the route answers. */
export function useProviders(enabled = true) {
  return useQuery({
    queryKey: providersKey,
    queryFn: async () => (await providersApi.list()).providers,
    enabled,
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

/** Which local runtime answers at `baseUrl` (null = each default port). A
 *  QUERY so the Add dialog shows its loading / error states; it runs only
 *  while `enabled` (the user chose the local path) and a Test re-asks it.
 *  `retry: false`: nothing answering is an answer. */
export function useDetectLocalRuntimes(baseUrl: string | null, enabled: boolean) {
  return useQuery({
    queryKey: localRuntimesKey(baseUrl),
    queryFn: () => providersApi.detectLocal(baseUrl),
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

// No onError toast: the Add dialog renders the failure inline under its form.
export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderCreate) => providersApi.create(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: providersKey });
      // The key goes only to an approved URL: a binding the registration could
      // not approve waits from now, so the approvals are read now.
      qc.invalidateQueries({ queryKey: pendingApprovalsKey });
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
      // A moved base URL asks again from the save.
      qc.invalidateQueries({ queryKey: pendingApprovalsKey });
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

/** Replace a provider's key; the new value is stored at once.
 *  No onError toast: the Replace dialog renders the failure inline. */
export function useReplaceProviderKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; secret: string }) =>
      providersApi.update(vars.uid, { secret_value: vars.secret }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: providersKey });
    },
  });
}

/** Point a provider at ANOTHER stored secret (its `secret_ref`); neither
 *  secret's value changes. Failures render inline in the Replace dialog. */
export function useRebindProviderKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { uid: string; secretRef: string }) =>
      providersApi.update(vars.uid, { secret_ref: vars.secretRef }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: providersKey });
      void qc.invalidateQueries({ queryKey: secretsListKey });
    },
  });
}

export function useDeleteProvider() {
  const qc = useQueryClient();
  const onError = useProviderToastError();
  return useMutation({
    mutationFn: (uid: string) => providersApi.remove(uid),
    // The detail and its endpoint probe go first, so a stale detail view
    // cannot refetch a 404; the row leaves the cached list at once, because
    // the page opens the list's first provider and must not reopen this one
    // before the refetch lands; then the list is refetched.
    onSuccess: (_data, uid) => {
      qc.removeQueries({ queryKey: providerKey(uid) });
      qc.removeQueries({ queryKey: endpointModelsKey(uid) });
      qc.setQueryData<Provider[]>(providersKey, (old) => old?.filter((p) => p.uid !== uid));
      void qc.invalidateQueries({ queryKey: providersKey });
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
