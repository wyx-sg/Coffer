// frontend/src/lib/mcp/editMcpServerSave.ts — the save path for the
// edit-server dialog.
//
// Extracted from the component because it is the part with the ordering rules,
// not the part with the markup: secrets are written BEFORE the resource PATCH
// so a rejected config never leaves the config pointing at a key that was
// never stored, and brand-new refs are rolled back when that PATCH fails so a
// rejected edit never orphans a secret.
//
// The PATCH is addressed to the server's uid. A new secret's ref is `secret/<uuid4 hex>`, minted
// by `@/lib/secretValue`; nothing here reads the server's NAME, which would make it a key into the
// encrypted store.
//
// Which row cites which ref is `serverRows.ts`; this file does the writes in order.
import type { TFunction } from "i18next";

import { resourcesApi } from "@/lib/api/resources";
import { secretsApi } from "@/lib/api/secret";
import type { components } from "@/lib/api/types";
import { persistNewSecrets, secretRef, type KeyValueSecretRow } from "@/lib/secretValue";
import {
  authSchemesField,
  keptRows,
  plainMapOfRows,
  secretRefsForSave,
  secretRefsOf,
} from "@/lib/mcp/serverRows";
import { withTimeouts, type Timeouts } from "@/lib/mcp/serverTimeouts";

type ResourceOut = components["schemas"]["ResourceOut"];

/** The config JSON minus the fields with their own controls — secrets and
 * the two timeouts. Both are merged back in on save. */
function configWithoutOwnControls(config: unknown): Record<string, unknown> {
  const clone = JSON.parse(JSON.stringify(config ?? {})) as Record<string, unknown>;
  const transport = clone.transport as Record<string, unknown> | undefined;
  if (transport) {
    delete transport.secret_refs;
    delete transport.auth_schemes;
  }
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
 *  plain rows land in `env` / `headers`; chosen secrets go to secret_refs. */
export interface TransportForm {
  type: "stdio" | "http";
  url: string;
  command: string;
  args: string[];
  cwd: string;
  rows: KeyValueSecretRow[];
}

/** The config JSON the save path takes: the stored config (minus the fields
 *  with their own controls) with the form's transport fields written over it,
 *  so every key the form does not show is kept as it was. */
export function configTextFrom(config: unknown, form: TransportForm): string {
  const base = configWithoutOwnControls(config);
  const transport = { ...((base.transport as Record<string, unknown>) ?? {}) };
  const plain = plainMapOfRows(form.rows);
  if (form.type === "http") {
    Object.assign(transport, { url: form.url.trim(), headers: plain });
    Object.assign(transport, authSchemesField(form.rows));
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
  /** Every Environment / Headers row; the secret ones are resolved here. */
  rows: KeyValueSecretRow[];
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
}: SaveArgs): Promise<void> {
  let config: Record<string, unknown>;
  try {
    config = JSON.parse(configText) as Record<string, unknown>;
  } catch {
    throw new Error(t("mcp.edit.errInvalidConfig"));
  }

  // Validated before any secret write: a new secret row without a value.
  const kept = keptRows(rows);
  for (const r of kept) {
    if (r.value.kind === "new" && r.value.value === "") {
      throw new Error(t("mcp.edit.errSecretNeedsValue", { name: r.key.trim() }));
    }
  }

  // The refs the config will cite (see `secretRefsForSave`).
  const secretRefs = secretRefsForSave(kept, secretRefsOf(resource.config));

  // Write new secrets first, so a rejected config never leaves the config
  // pointing at a secret that was never stored; they are removed again when the
  // PATCH below fails.
  const newlyWrittenRefs: string[] = [];
  for (const r of kept) {
    if (r.value.kind !== "new") continue;
    newlyWrittenRefs.push(secretRef(r.value.name));
    await persistNewSecrets([r.value]);
  }

  const transport = {
    ...((config.transport as Record<string, unknown>) ?? {}),
    secret_refs: secretRefs,
  };
  try {
    await resourcesApi.update(resource.uid, {
      description: description.trim() || null,
      ...(title === undefined ? {} : { title: title.trim() || null }),
      config: withTimeouts({ ...config, transport }, timeouts),
    });
  } catch (e) {
    // PATCH rejected the config — delete the new secrets we just wrote so they
    // don't dangle (best-effort).
    for (const ref of newlyWrittenRefs) {
      try {
        await secretsApi.remove(ref);
      } catch (cleanup) {
        console.warn(`[EditMcpServerDialog] rollback delete failed for ${ref}:`, cleanup);
      }
    }
    throw e;
  }

  // A secret this server no longer cites is not deleted from here: every secret is
  // `secret/<id>`, so the ref's shape no longer says whom it was minted for. The daemon releases
  // a ref when the resource that created it goes, and an unused one is deletable from the
  // Secrets page.
}
