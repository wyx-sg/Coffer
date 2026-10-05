// frontend/src/pages/sync/useStorePushToken.ts
//
// Resolve the push token's field before the remote is checked or saved: a
// pasted token is written to Secrets (its listing refreshed, so the field names
// it at once) and the form comes back citing it. Rejects, writing nothing more,
// when the store refuses it.
import { useQueryClient } from "@tanstack/react-query";

import { secretsKey } from "@/lib/api/queryKeys";
import { withSecretStored, type FormState } from "./syncRemoteForm";

export function useStorePushToken() {
  const qc = useQueryClient();
  return async (form: FormState): Promise<FormState> => {
    const stored = await withSecretStored(form);
    if (stored !== form) void qc.invalidateQueries({ queryKey: secretsKey });
    return stored;
  };
}
