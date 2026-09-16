// frontend/src/components/mcp/importMcpServers.ts
// The plumbing behind "Add MCP server": turn each parsed JSON server into a
// Coffer config plus credential writes, register it, and roll it back when
// its secrets cannot be stored. Pure functions + one async batch, so the
// dialog stays a view and the mutation hook (useMcpServerMutations.ts) stays
// one line.
import type { TFunction } from "i18next";

import { getApiClient } from "@/lib/api/client";
import { throwApiError, translateApiError } from "@/lib/api/errors";
import type { ParsedServer } from "./jsonImport";

interface ServerPlan {
  config: Record<string, unknown>;
  secrets: { ref: string; value: string }[];
}

/**
 * Turn a parsed JSON server into a Coffer config plus the list of
 * credential writes to perform. Pure (no network) — so the config is fully
 * built before any side effect runs. Secret env vars become
 * `credential_refs`; non-secret values stay inline — in `env` for stdio,
 * in `headers` for http (HttpTransport has no `env` field), mirroring how
 * the secret path already routes to each transport's credential_refs.
 */
function planServer(srv: ParsedServer): ServerPlan {
  const credentialRefs: Record<string, string> = {};
  const plain: Record<string, string> = {};
  const secrets: { ref: string; value: string }[] = [];
  for (const e of srv.env) {
    if (e.isSecret) {
      const ref = `${srv.name}.${e.key}`;
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

async function registerResource(name: string, config: Record<string, unknown>): Promise<void> {
  const client = getApiClient();
  const { error } = await client.POST("/resources", {
    body: { kind: "mcp_server", name, config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
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
async function rollbackResource(name: string): Promise<void> {
  try {
    const client = getApiClient();
    await client.DELETE("/resources/{kind}/{name}", {
      params: { path: { kind: "mcp_server", name } },
    });
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

export interface ImportMcpServersArgs {
  servers: ParsedServer[];
  /** Names already registered by a prior attempt of THIS import session, so a
   *  retry after a partial failure re-attempts only the servers that failed
   *  instead of re-POSTing the created ones (which would 409). Mutated in
   *  place as servers succeed. */
  created: Set<string>;
  t: TFunction;
}

/**
 * Import a batch. Each server is registered before its secrets are written
 * to the encrypted credential store, so a failed registration leaves nothing
 * orphaned; a failed secret write rolls the registration back. Resolves with
 * the names created; rejects with a BatchImportError naming every server that
 * failed (the ones that did register stay registered).
 */
export async function importMcpServers({
  servers,
  created,
  t,
}: ImportMcpServersArgs): Promise<string[]> {
  const done: string[] = [];
  const failed: string[] = [];
  for (const srv of servers) {
    if (created.has(srv.name)) {
      done.push(srv.name);
      continue;
    }
    const { config, secrets } = planServer(srv);
    let registered = false;
    try {
      await registerResource(srv.name, config);
      registered = true;
      for (const s of secrets) {
        await writeCredential(s.ref, s.value);
      }
      created.add(srv.name);
      done.push(srv.name);
    } catch (e) {
      // Secret write failed after registration — roll the resource back so we
      // don't leave a Coffer server pointing at a credential ref that was
      // never stored in the encrypted store.
      if (registered) {
        await rollbackResource(srv.name);
      }
      failed.push(`${srv.name}: ${translateApiError(t, e)}`);
    }
  }
  if (failed.length > 0) throw new BatchImportError(failed);
  return done;
}
