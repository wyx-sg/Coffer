// frontend/src/components/channel/registerChannel.ts
// Registration plumbing for AddChannelDialog: secrets are written to the
// credential store FIRST (registration probes the refs — see "Register
// channels as a credential-referencing resource kind"), then the
// resource is registered; on failure the just-written secrets are rolled
// back so nothing orphaned stays behind.
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { ResourceOut } from "@/lib/api/resources";

import type { ChannelPlan } from "./schema";

async function writeSecret(ref: string, value: string): Promise<void> {
  const { error } = await getApiClient().POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

/** Best-effort rollback of secrets written before a failed registration. */
async function rollbackSecrets(refs: string[]): Promise<void> {
  for (const ref of refs) {
    try {
      await getApiClient().DELETE("/credentials/{ref}", { params: { path: { ref } } });
    } catch (e) {
      console.warn(`[AddChannelDialog] rollback delete failed for ${ref}:`, e);
    }
  }
}

async function registerResource(plan: ChannelPlan): Promise<ResourceOut> {
  const { data, error } = await getApiClient().POST("/resources", {
    body: { kind: "channel", name: plan.name, config: plan.config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty register response");
  return data;
}

/**
 * Fail BEFORE any secret write when the name is taken: writing first would
 * overwrite the live channel's secret and then roll it back (deleting it),
 * leaving the existing channel dead on its next restart.
 *
 * The check is a scan of the channel list rather than a lookup, because a
 * resource is no longer addressable by name: there is no `GET` that takes one.
 * That is the right shape anyway — the question here is "is this LABEL taken",
 * which is a question about the set of labels, not about one row.
 */
async function assertNameAvailable(name: string): Promise<void> {
  const { data } = await getApiClient().GET("/resources", {
    params: { query: { kind: "channel" } },
  });
  if ((data?.resources ?? []).some((r) => r.name === name)) {
    throwApiError(
      { error: { code: "RESOURCE_ALREADY_EXISTS", message: `channel ${name} already exists` } },
      "RESOURCE_ALREADY_EXISTS",
      "name already in use",
    );
  }
}

/**
 * Secrets-then-resource registration with rollback.
 *
 * Returns the registered resource, not its name: the caller navigates to the
 * new channel's page, and that URL is built from the uid.
 */
export async function createChannel(plan: ChannelPlan): Promise<ResourceOut> {
  await assertNameAvailable(plan.name);
  const written: string[] = [];
  try {
    for (const s of plan.secrets) {
      await writeSecret(s.ref, s.value);
      written.push(s.ref);
    }
    return await registerResource(plan);
  } catch (e) {
    await rollbackSecrets(written);
    throw e;
  }
}
