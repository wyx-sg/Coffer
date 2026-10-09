// src/components/providers/labelNewKey.ts — name the secret a pasted provider key became.
import type { QueryClient } from "@tanstack/react-query";

import { secretsApi } from "@/lib/api/secret";
import { secretsKey } from "@/lib/api/queryKeys";
import type { SecretFieldValue } from "@/lib/secretValue";

/** A pasted key is stored by the daemon under a ref it mints; give it the name the field showed.
 *  A nicety: the provider is added either way, so a failure here only logs. The secrets are read
 *  again after the label write (not only after the create), so every link to the new key shows
 *  its name without a reload. */
export async function labelNewKey(qc: QueryClient, secret: SecretFieldValue, ref: string | null) {
  const label = secret?.kind === "new" ? secret.label.trim() : "";
  if (!ref) return;
  try {
    if (label) await secretsApi.setNotes(ref, { label });
  } catch (e) {
    console.warn(`[AddProviderDialog] could not label ${ref}:`, e);
  } finally {
    void qc.invalidateQueries({ queryKey: secretsKey });
  }
}
