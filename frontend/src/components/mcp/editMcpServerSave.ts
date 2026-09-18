// frontend/src/components/mcp/editMcpServerSave.ts — the save path for the
// edit-server dialog.
//
// Extracted from the component because it is the part with the ordering rules,
// not the part with the markup: secrets are written BEFORE the resource PATCH
// so a rejected config never leaves the config pointing at a key that was
// never stored, and brand-new refs are rolled back when that PATCH fails so a
// rejected edit never orphans a secret.
//
// The PATCH is addressed to the server's uid, and so are the credential refs:
// `mcp_server/<uuid4 hex>/<key>`, minted by `@/lib/credentialRef`. Nothing here
// reads the server's NAME any more. It used to, twice — refs were built as
// `<name>.<key>` and the orphan cleanup below decided which refs this server
// owned by testing for that same `<name>.` prefix — and the pair of them made
// the name a key into the encrypted store: rename the server and its own refs
// stopped looking like its own. That was unreachable only while `mcp_server`
// could not be renamed at all; rename is now a field on `PATCH
// /resources/{uid}` for every kind, which is what reached it.
import type { TFunction } from "i18next";

import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { isMintedCredentialRef, mintCredentialRef } from "@/lib/credentialRef";
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
 * the two timeouts. Both are merged back in on save, so the textarea never
 * competes with a structured field over the same key. */
export function configWithoutOwnControls(config: unknown): string {
  const clone = JSON.parse(JSON.stringify(config ?? {})) as Record<string, unknown>;
  const transport = clone.transport as Record<string, unknown> | undefined;
  if (transport) delete transport.credential_refs;
  delete clone.spawn_timeout_seconds;
  delete clone.request_timeout_seconds;
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
      // Rotating an existing row writes THROUGH its existing ref; only a row
      // with no ref yet, or one whose key was renamed (so its ref's trailing
      // label would lie), gets a freshly minted address. Minting on every
      // rotation would move the secret, and a move crosses the sync remote as
      // a delete plus an add of something the other machine cannot place.
      const ref =
        row.originalRef && row.originalName === name
          ? row.originalRef
          : mintCredentialRef("mcp_server", name);
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
  const { error: pe } = await client.PATCH("/resources/{uid}", {
    params: { path: { uid: resource.uid } },
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

  // Clean up credential store entries this server no longer references — but
  // only ones Coffer minted for it, never a ref the user typed or pasted here
  // to share one secret between two servers. Ownership is the ref's SHAPE, not
  // the server's name: a minted ref carries a uuid nothing else produced, and
  // it keeps meaning that after a rename, which the old `<name>.` prefix test
  // did not. A failed cleanup must not roll back the successful PATCH above;
  // we log a warning and let the user re-trigger if needed.
  const newRefs = new Set(Object.values(credentialRefs));
  const orphanWarnings: string[] = [];
  for (const ref of Object.values(credentialRefsOf(resource.config))) {
    if (!newRefs.has(ref) && isMintedCredentialRef("mcp_server", ref)) {
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
