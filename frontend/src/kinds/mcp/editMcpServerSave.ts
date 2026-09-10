// frontend/src/kinds/mcp/editMcpServerSave.ts — the save path for the
// edit-server dialog.
//
// Extracted from the component because it is the part with the ordering rules,
// not the part with the markup: secrets are written BEFORE the resource PATCH
// so a rejected config never leaves the config pointing at a key that was
// never stored, and brand-new refs are rolled back when that PATCH fails so a
// rejected edit never orphans a secret.
import type { TFunction } from "i18next";

import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import type { CredRow } from "./CredentialRowEditor";
import { withTimeouts, type Timeouts } from "./serverTimeouts";

type ResourceOut = components["schemas"]["ResourceOut"];

export function credentialRefsOf(config: unknown): Record<string, string> {
  const transport = (config as Record<string, unknown> | null)?.transport;
  const refs = (transport as Record<string, unknown> | undefined)?.credential_refs;
  const out: Record<string, string> = {};
  if (refs && typeof refs === "object") {
    for (const [k, v] of Object.entries(refs)) {
      if (typeof v === "string") out[k] = v;
    }
  }
  return out;
}

/** The config JSON minus the fields with their own controls — credentials and
 * the three timeouts. Both are merged back in on save, so the textarea never
 * competes with a structured field over the same key. */
export function configWithoutOwnControls(config: unknown): string {
  const clone = JSON.parse(JSON.stringify(config ?? {})) as Record<string, unknown>;
  const transport = clone.transport as Record<string, unknown> | undefined;
  if (transport) delete transport.credential_refs;
  delete clone.spawn_timeout_seconds;
  delete clone.request_timeout_seconds;
  delete clone.idle_timeout_seconds;
  return JSON.stringify(clone, null, 2);
}

export interface SaveArgs {
  resource: ResourceOut;
  description: string;
  configText: string;
  creds: CredRow[];
  timeouts: Timeouts;
  t: TFunction;
}

export async function saveMcpServerEdit({
  resource,
  description,
  configText,
  creds,
  timeouts,
  t,
}: SaveArgs): Promise<{ orphanWarnings: string[] }> {
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(configText) as Record<string, unknown>;
    } catch {
      throw new Error(t("mcp.import.errInvalidJson"));
    }
    const client = getApiClient();

    // Pre-validate before any credential write: a row renamed without a
    // new value can't be moved in the encrypted store blind (we don't hold
    // the plaintext), so require the secret to be re-entered under the new
    // name rather than silently leaving the ref pointing at the old name.
    for (const row of creds) {
      const name = row.name.trim();
      if (name === "" || row.value !== "" || !row.originalRef) continue;
      if (row.originalName !== null && name !== row.originalName) {
        throw new Error(t("mcp.edit.errRenameNeedsValue", { name }));
      }
    }

    // Build credential_refs; write new / rotated secret values first.
    // Track credential refs we create that are BRAND NEW (not a rotation
    // of an existing ref) so we can clean them up if the PATCH below
    // fails — otherwise a config the backend rejects would orphan the secret.
    const originalRefSet = new Set(Object.values(credentialRefsOf(resource.config)));
    const credentialRefs: Record<string, string> = {};
    const newlyWrittenRefs: string[] = [];
    for (const row of creds) {
      const name = row.name.trim();
      if (name === "") continue;
      if (row.value !== "") {
        const ref = `${resource.name}.${name}`;
        const { error: e } = await client.POST("/credentials", {
          body: { ref, value: row.value },
        });
        if (e) throwApiError(e, "INTERNAL_ERROR", "credential write failed");
        credentialRefs[name] = ref;
        if (!originalRefSet.has(ref)) newlyWrittenRefs.push(ref);
      } else if (row.originalRef) {
        // Unchanged name → keep the existing secret under its ref.
        credentialRefs[name] = row.originalRef;
      }
    }

    const transport = {
      ...((config.transport as Record<string, unknown>) ?? {}),
      credential_refs: credentialRefs,
    };
    const { error: pe } = await client.PATCH("/resources/{kind}/{name}", {
      params: { path: { kind: "mcp_server", name: resource.name } },
      body: {
        description: description.trim() || null,
        config: withTimeouts({ ...config, transport }, timeouts),
      },
    });
    if (pe) {
      // PATCH rejected the config — delete the brand-new credential entries
      // we just wrote so they don't dangle (best-effort; rotations of
      // existing refs are left, since the unchanged config still uses them).
      for (const ref of newlyWrittenRefs) {
        try {
          await client.DELETE("/credentials/{ref}", { params: { path: { ref } } });
        } catch {
          // best-effort cleanup; the PATCH error below is what matters
        }
      }
      throwApiError(pe, "INTERNAL_ERROR", "update failed");
    }

    // Clean up credential store entries this server no longer references —
    // but only ones it owns (`<name>.` prefix); never a shared/manual ref.
    // A failed cleanup must not roll back the successful PATCH above;
    // we log a warning and let the user re-trigger if needed.
    const newRefs = new Set(Object.values(credentialRefs));
    const prefix = `${resource.name}.`;
    const orphanWarnings: string[] = [];
    for (const ref of Object.values(credentialRefsOf(resource.config))) {
      if (!newRefs.has(ref) && ref.startsWith(prefix)) {
        const { error: de } = await client.DELETE("/credentials/{ref}", {
          params: { path: { ref } },
        });
        if (de) {
          const msg = de.error?.message ?? "credential delete failed";
          console.warn(`[EditMcpServerDialog] orphan cleanup failed for ${ref}:`, msg);
          orphanWarnings.push(ref);
        }
      }
    }
    return { orphanWarnings };
}
