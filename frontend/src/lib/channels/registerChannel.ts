// frontend/src/lib/channels/registerChannel.ts
// Registration plumbing for AddChannelDialog: secrets are written to the
// secret store FIRST (registration probes the refs — see "Register
// channels as a secret-referencing resource kind"), then the
// resource is registered; on failure the just-written secrets are rolled
// back so nothing orphaned stays behind.
//
// The name the person typed is a display name (spec channels "Name a channel by
// any display name") and is registered as the channel's `name` as typed; a name
// already taken is the daemon's 409 RESOURCE_ALREADY_EXISTS, shown on the form.
import { secretsApi } from "@/lib/api/secret";
import { resourcesApi, type ResourceOut } from "@/lib/api/resources";
import { writeSecret } from "@/lib/secretWrite";

import type { ChannelPlan } from "@/lib/channels/schema";

/** Best-effort rollback of secrets written before a failed registration. A
 *  delete the daemon refuses is logged and the rest still go: the registration
 *  failure is what the person acts on. */
async function rollbackSecrets(refs: string[]): Promise<void> {
  for (const ref of refs) {
    try {
      await secretsApi.remove(ref);
    } catch (e) {
      console.warn(`[AddChannelDialog] rollback delete failed for ${ref}:`, e);
    }
  }
}

/** Name a new secret after what the field showed. A nicety: the secret is stored and cited either
 *  way, so a failure only logs. */
async function labelSecret(ref: string, label: string): Promise<void> {
  try {
    await secretsApi.setNotes(ref, { label });
  } catch (e) {
    console.warn(`[AddChannelDialog] could not label ${ref}:`, e);
  }
}

/**
 * Secrets-then-resource registration with rollback.
 *
 * Returns the registered resource, not its name: the caller navigates to the
 * new channel's page, and that URL is built from the uid.
 */
export async function createChannel(plan: ChannelPlan): Promise<ResourceOut> {
  const written: string[] = [];
  try {
    for (const s of plan.secrets) {
      await writeSecret(s.ref, s.value);
      written.push(s.ref);
    }
    const created = await resourcesApi.create({
      kind: "channel",
      name: plan.name,
      config: plan.config,
    });
    for (const s of plan.secrets) if (s.label?.trim()) await labelSecret(s.ref, s.label.trim());
    return created;
  } catch (e) {
    await rollbackSecrets(written);
    throw e;
  }
}
