// src/components/providers/labelNewKey.ts — name the secret a pasted provider key became.
import { secretsApi } from "@/lib/api/secret";
import type { SecretFieldValue } from "@/lib/secretValue";

/** A pasted key is stored by the daemon under a ref it mints; give it the name the field showed.
 *  A nicety: the provider is added either way, so a failure here only logs. */
export async function labelNewKey(secret: SecretFieldValue, ref: string | null) {
  const label = secret?.kind === "new" ? secret.label.trim() : "";
  if (!label || !ref) return;
  try {
    await secretsApi.setNotes(ref, { label });
  } catch (e) {
    console.warn(`[AddProviderDialog] could not label ${ref}:`, e);
  }
}
