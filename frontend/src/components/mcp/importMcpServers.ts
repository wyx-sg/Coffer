// frontend/src/components/mcp/importMcpServers.ts
// The plumbing behind "Add MCP server": turn each parsed JSON server into a
// Coffer config plus credential writes, register it, and roll it back when
// its secrets cannot be stored. Pure functions + one async batch, so the
// dialog stays a view and the mutation hook (useMcpServerMutations.ts) stays
// one line.
import type { TFunction } from "i18next";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError, translateApiError } from "@/lib/api/errors";
import { mintCredentialRef } from "@/lib/credentialRef";
import type { ParsedServer } from "./jsonImport";

interface ServerPlan {
  config: Record<string, unknown>;
  secrets: { ref: string; value: string }[];
}

/**
 * Turn a parsed JSON server into a Coffer config plus the list of
 * credential writes to perform. Pure (no network) — so the config is fully
 * built before any side effect runs. Secret values become
 * `credential_refs`; non-secret values stay inline — in `env` for stdio,
 * in `headers` for http (the parser has already gathered an http server's
 * `headers` block, and any `env` block, into `srv.env`; HttpTransport has no
 * `env` field), mirroring how the secret path routes to each transport's
 * credential_refs.
 *
 * Each secret's ref is minted opaque (`mcp_server/<uuid4 hex>/<env key>`) and
 * NOT from the server's name, which is what `<name>.<env key>` used to do. A
 * server can now be renamed like every other resource, and a ref built from the
 * name would be left describing a label the resource no longer has — while the
 * secret itself sits in the encrypted store under the old address, reachable
 * only because something still cites it.
 */
function planServer(srv: ParsedServer): ServerPlan {
  const credentialRefs: Record<string, string> = {};
  const plain: Record<string, string> = {};
  const secrets: { ref: string; value: string }[] = [];
  for (const e of srv.env) {
    if (e.isSecret) {
      const ref = mintCredentialRef("mcp_server", e.key);
      credentialRefs[e.key] = ref;
      secrets.push({ ref, value: e.value });
    } else {
      plain[e.key] = e.value;
    }
  }
  const transport =
    srv.transportType === "stdio"
      ? {
          type: "stdio",
          command: srv.command,
          args: srv.args,
          env: plain,
          credential_refs: credentialRefs,
        }
      : { type: "http", url: srv.url, headers: plain, credential_refs: credentialRefs };
  return { config: { transport }, secrets };
}

/** Registers the server and returns its uid — which is what a rollback needs:
 *  the resource is addressed by identity, and the name it was registered under
 *  is only how the failure is reported. */
async function registerResource(name: string, config: Record<string, unknown>): Promise<string> {
  const client = getApiClient();
  const { data, error } = await client.POST("/resources", {
    body: { kind: "mcp_server", name, config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty register response");
  return data.uid;
}

async function writeCredential(ref: string, value: string): Promise<void> {
  const client = getApiClient();
  const { error } = await client.POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "credential write failed");
}

/**
 * Best-effort rollback of a just-registered resource whose secret writes
 * failed. We try to leave nothing behind referencing a credential that
 * was never stored; any cleanup error is logged but not surfaced — the
 * primary failure (the secret write) is what the user needs to act on.
 */
async function rollbackResource(uid: string, name: string): Promise<void> {
  try {
    const client = getApiClient();
    await client.DELETE("/resources/{uid}", { params: { path: { uid } } });
  } catch (e) {
    console.warn(`[importMcpServers] rollback delete failed for ${name}:`, e);
  }
}

/** A batch that partly failed: the servers that did register stay; the
 * dialog lists every one that did not, one line each. */
export class BatchImportError extends Error {
  constructor(readonly failed: string[]) {
    super(failed.join("; "));
    this.name = "BatchImportError";
  }
}

/** One server this import registered: the name the batch named it, and the uid
 *  it now has — which is what a caller follows to its page. */
export interface ImportedServer {
  name: string;
  uid: string;
}

export interface ImportMcpServersArgs {
  servers: ParsedServer[];
  /** What a prior attempt of THIS import session already registered, keyed by
   *  the name the pasted batch used, so a retry after a partial failure
   *  re-attempts only the servers that failed instead of re-POSTing the created
   *  ones (which would 409). Mutated in place as servers succeed.
   *
   *  A map rather than a set of names: the uid is the half a caller acts on,
   *  and a retry that skips an already-registered server still has to report
   *  it. Keyed by NAME because that is what the pasted document says, and the
   *  question being asked here is "did this batch already register this
   *  entry" — a question about the input, not about a resource. */
  created: Map<string, string>;
  t: TFunction;
}

/**
 * Import a batch. Each server is registered before its secrets are written
 * to the encrypted credential store, so a failed registration leaves nothing
 * orphaned; a failed secret write rolls the registration back. Resolves with
 * the servers created; rejects with a BatchImportError naming every server that
 * failed (the ones that did register stay registered).
 */
export async function importMcpServers({
  servers,
  created,
  t,
}: ImportMcpServersArgs): Promise<ImportedServer[]> {
  const done: ImportedServer[] = [];
  const failed: string[] = [];
  for (const srv of servers) {
    const already = created.get(srv.name);
    if (already !== undefined) {
      done.push({ name: srv.name, uid: already });
      continue;
    }
    const { config, secrets } = planServer(srv);
    // The uid the registration returned, and the handle a rollback needs;
    // `null` while nothing has been registered yet.
    let registeredUid: string | null = null;
    try {
      registeredUid = await registerResource(srv.name, config);
      for (const s of secrets) {
        await writeCredential(s.ref, s.value);
      }
      created.set(srv.name, registeredUid);
      done.push({ name: srv.name, uid: registeredUid });
    } catch (e) {
      // Secret write failed after registration — roll the resource back so we
      // don't leave a Coffer server pointing at a credential ref that was
      // never stored in the encrypted store.
      if (registeredUid !== null) {
        await rollbackResource(registeredUid, srv.name);
      }
      failed.push(`${srv.name}: ${translateApiError(t, e)}`);
    }
  }
  if (failed.length > 0) throw new BatchImportError(failed);
  return done;
}
