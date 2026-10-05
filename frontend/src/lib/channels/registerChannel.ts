// frontend/src/lib/channels/registerChannel.ts
// Registration plumbing for AddChannelDialog: secrets are written to the
// secret store FIRST (registration probes the refs — see "Register
// channels as a secret-referencing resource kind"), then the
// resource is registered; on failure the just-written secrets are rolled
// back so nothing orphaned stays behind.
//
// The name the person typed is a display name (spec channels "Name a channel by
// any display name"): it is registered as the channel's title, and the
// resource's name is derived from it, made unique among the channels that
// exist, so the add never fails on a label the person never saw.
import { secretsApi } from "@/lib/api/secret";
import { resourcesApi, type ResourceOut } from "@/lib/api/resources";
import { writeSecret } from "@/lib/secretWrite";

import { channelSlug, type ChannelPlan } from "@/lib/channels/schema";

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
 * The resource name for this display name, clear of every channel's name.
 *
 * Chosen BEFORE any secret write: registering under a taken name would fail
 * after the secrets were written. A resource is not addressable by name, so
 * the check is a scan of the channel list — the question is "which labels are
 * taken", a question about the set. A list that cannot be read throws: a name
 * picked against an empty list would collide after the secrets were stored.
 */
async function freeName(displayName: string): Promise<string> {
  const { resources } = await resourcesApi.list("channel");
  return channelSlug(
    displayName,
    resources.map((r) => r.name),
  );
}

/**
 * Secrets-then-resource registration with rollback.
 *
 * Returns the registered resource, not its name: the caller navigates to the
 * new channel's page, and that URL is built from the uid.
 */
export async function createChannel(plan: ChannelPlan): Promise<ResourceOut> {
  const name = await freeName(plan.name);
  const written: string[] = [];
  try {
    for (const s of plan.secrets) {
      await writeSecret(s.ref, s.value);
      written.push(s.ref);
    }
    const created = await resourcesApi.create({
      kind: "channel",
      name,
      title: plan.name,
      config: plan.config,
    });
    for (const s of plan.secrets) if (s.label?.trim()) await labelSecret(s.ref, s.label.trim());
    return created;
  } catch (e) {
    await rollbackSecrets(written);
    throw e;
  }
}
