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
// reads the server's NAME: a ref built from the name would make the name a key
// into the encrypted store, and rename is a field on `PATCH /resources/{uid}`.
//
// Which Secret row cites which ref, and which typed value is written where, is
// `env/rowsModel.ts` (`secretPlanOf`); this file does the writes in order.
import type { TFunction } from "i18next";

import { getApiClient } from "@/lib/api/client";
import { throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { isMintedCredentialRef, mintCredentialRef } from "@/lib/credentialRef";
import type { ParsedEnvVar } from "@/lib/mcp/pasteTypes";
import { credentialRefsOf, plainMapOf, secretPlanOf } from "./env/rowsModel";
import { withTimeouts, type Timeouts } from "./serverTimeouts";

export { credentialRefsOf } from "./env/rowsModel";

type ResourceOut = components["schemas"]["ResourceOut"];

/** The config JSON minus the fields with their own controls — credentials and
 * the two timeouts. Both are merged back in on save. */
function configWithoutOwnControls(config: unknown): Record<string, unknown> {
  const clone = JSON.parse(JSON.stringify(config ?? {})) as Record<string, unknown>;
  const transport = clone.transport as Record<string, unknown> | undefined;
  if (transport) delete transport.credential_refs;
  delete clone.spawn_timeout_seconds;
  delete clone.request_timeout_seconds;
  return clone;
}

/** The transport fields the edit form shows as fields: where the server is
 *  reached (URL, or command + arguments + working directory) and its plain,
 *  non-secret values (a stdio server's `env`, an HTTP server's `headers`). */
export interface TransportFields {
  type: "stdio" | "http";
  url: string;
  command: string;
  args: string[];
  /** stdio: the folder the command starts in; "" = not set. */
  cwd: string;
  plain: { key: string; value: string }[];
}

function stringMap(raw: unknown): { key: string; value: string }[] {
  if (!raw || typeof raw !== "object") return [];
  return Object.entries(raw as Record<string, unknown>)
    .filter(([, v]) => typeof v === "string")
    .map(([key, value]) => ({ key, value: value as string }));
}

export function transportFieldsOf(config: unknown): TransportFields {
  const tr = ((config as Record<string, unknown> | null)?.transport ?? {}) as Record<
    string,
    unknown
  >;
  const http = tr.type === "http";
  return {
    type: http ? "http" : "stdio",
    url: typeof tr.url === "string" ? tr.url : "",
    command: typeof tr.command === "string" ? tr.command : "",
    args: Array.isArray(tr.args) ? tr.args.map(String) : [],
    cwd: typeof tr.cwd === "string" ? tr.cwd : "",
    plain: stringMap(http ? tr.headers : tr.env),
  };
}

/** What the form holds for the transport: its fields and every row. Only the
 *  Plain rows land in `env` / `headers`; Secret rows go to credential_refs. */
export interface TransportForm {
  type: "stdio" | "http";
  url: string;
  command: string;
  args: string[];
  cwd: string;
  rows: ParsedEnvVar[];
}

/** The config JSON the save path takes: the stored config (minus the fields
 *  with their own controls) with the form's transport fields written over it,
 *  so every key the form does not show is kept as it was. */
export function configTextFrom(config: unknown, form: TransportForm): string {
  const base = configWithoutOwnControls(config);
  const transport = { ...((base.transport as Record<string, unknown>) ?? {}) };
  const plain = plainMapOf(form.rows);
  if (form.type === "http") {
    Object.assign(transport, { url: form.url.trim(), headers: plain });
  } else {
    Object.assign(transport, { command: form.command.trim(), args: form.args, env: plain });
    const cwd = form.cwd.trim();
    if (cwd === "") delete transport.cwd;
    else transport.cwd = cwd;
  }
  return JSON.stringify({ ...base, transport });
}

export interface SaveArgs {
  resource: ResourceOut;
  description: string;
  /** The title to store; left out, the stored title is not touched. */
  title?: string;
  configText: string;
  /** Every Environment / Headers row; the Secret ones are resolved here. */
  rows: ParsedEnvVar[];
  timeouts: Timeouts;
  t: TFunction;
}

export async function saveMcpServerEdit({
  resource,
  description,
  configText,
  rows,
  timeouts,
  title,
  t,
}: SaveArgs): Promise<{ orphanWarnings: string[]; awaitingApproval: boolean }> {
  let config: Record<string, unknown>;
  try {
    config = JSON.parse(configText) as Record<string, unknown>;
  } catch {
    throw new Error(t("mcp.edit.errInvalidConfig"));
  }
  const client = getApiClient();

  // Validated before any credential write: a Secret row with neither a value
  // nor a stored secret, or one renamed while it keeps its own stored secret
  // (we don't hold the plaintext to move it), is refused here.
  const plan = secretPlanOf(rows, t);

  // Write new / rotated secret values first. Track the refs that are BRAND NEW
  // (not a rotation of an existing ref) so they can be cleaned up if the PATCH
  // below fails — otherwise a config the backend rejects would orphan them.
  const originalRefSet = new Set(Object.values(credentialRefsOf(resource.config)));
  const credentialRefs: Record<string, string> = { ...plan.cited };
  const newlyWrittenRefs: string[] = [];
  // Set when the daemon answered 202: a new value replaces one in use, so it is
  // stored sealed and waits for approval in the Coffer app.
  let awaitingApproval = false;
  for (const typed of plan.typed) {
    const ref = typed.rotate ?? mintCredentialRef("mcp_server", typed.key);
    const { data: written, error: e } = await client.POST("/credentials", {
      body: { ref, value: typed.value },
    });
    if (e) throwApiError(e, "INTERNAL_ERROR", "credential write failed");
    if (written?.approval !== undefined) awaitingApproval = true;
    credentialRefs[typed.key] = ref;
    if (!originalRefSet.has(ref)) newlyWrittenRefs.push(ref);
  }

  const transport = {
    ...((config.transport as Record<string, unknown>) ?? {}),
    credential_refs: credentialRefs,
  };
  const { error: pe } = await client.PATCH("/resources/{uid}", {
    params: { path: { uid: resource.uid } },
    body: {
      description: description.trim() || null,
      ...(title === undefined ? {} : { title: title.trim() || null }),
      config: withTimeouts({ ...config, transport }, timeouts),
    },
  });
  if (pe) {
    // PATCH rejected the config — delete the brand-new credential entries we
    // just wrote so they don't dangle (best-effort; rotations of existing refs
    // are left, since the unchanged config still uses them).
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
  // only ones Coffer minted for it, never a Secrets-page secret or a ref the
  // user wrote by hand to share one secret between two servers. Ownership is
  // the ref's SHAPE (a minted ref carries a uuid nothing else produced), not
  // the server's name. A failed cleanup must not roll back the PATCH above.
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
  return { orphanWarnings, awaitingApproval };
}
