// frontend/src/components/channel/registerChannel.ts
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
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";

import { channelSlug, type ChannelPlan } from "./schema";

async function writeSecret(ref: string, value: string): Promise<void> {
  const { error } = await getApiClient().POST("/secrets", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "secret write failed");
}

/** Best-effort rollback of secrets written before a failed registration. */
async function rollbackSecrets(refs: string[]): Promise<void> {
  for (const ref of refs) {
    try {
      await getApiClient().DELETE("/secrets/{ref}", { params: { path: { ref } } });
    } catch (e) {
      console.warn(`[AddChannelDialog] rollback delete failed for ${ref}:`, e);
    }
  }
}

async function registerResource(plan: ChannelPlan, name: string): Promise<ResourceOut> {
  const { data, error } = await getApiClient().POST("/resources", {
    body: { kind: "channel", name, title: plan.name, config: plan.config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty register response");
  return data;
}

/**
 * The resource name for this display name, clear of every channel's name.
 *
 * Chosen BEFORE any secret write: registering under a taken name would fail
 * after the secrets were written. A resource is not addressable by name, so
 * the check is a scan of the channel list — the question is "which labels are
 * taken", a question about the set.
 */
async function freeName(displayName: string): Promise<string> {
  const { data } = await getApiClient().GET("/resources", {
    params: { query: { kind: "channel" } },
  });
  return channelSlug(
    displayName,
    (data?.resources ?? []).map((r) => r.name),
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
    return await registerResource(plan, name);
  } catch (e) {
    await rollbackSecrets(written);
    throw e;
  }
}
