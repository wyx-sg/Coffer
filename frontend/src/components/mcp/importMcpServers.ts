// frontend/src/components/mcp/importMcpServers.ts
// The plumbing behind "Add MCP server": turn each parsed server into a Coffer
// config plus credential writes, register it, write its secrets (rolling the
// registration back when they cannot be stored), then give it its reach.
// Pure functions + one async batch, so the dialog stays a view and the
// mutation hook (useMcpServerMutations.ts) stays one line.
import type { TFunction } from "i18next";

import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError, translateApiError } from "@/lib/api/errors";
import { scopeApi } from "@/lib/api/scope";
import { mintCredentialRef } from "@/lib/credentialRef";
import type { ParsedServer } from "@/lib/mcp/pasteParse";

/** One server as the dialog confirmed it: the parsed shape plus the title
 *  the user may have typed (`""` = none). */
export interface NewServer extends ParsedServer {
  title?: string;
}

/** Which agents the new servers reach: every agent (no scope written), the
 *  ticked ones (a scope), or none (registered switched off). */
export type ReachIntent =
  | { mode: "everywhere" }
  | { mode: "restricted"; agents: string[] }
  | { mode: "disabled" };

interface ServerPlan {
  config: Record<string, unknown>;
  secrets: { ref: string; value: string }[];
}

/** The secret keys of `srv` still without a value — a `bearer_token_env_var`
 *  header arrives that way. The dialog asks for them; nothing is sent while
 *  any is empty, so an empty secret never reaches the credential store. */
export function missingSecretValues(srv: ParsedServer): string[] {
  return srv.env.filter((e) => e.isSecret && e.value === "").map((e) => e.key);
}

/**
 * A parsed server as a Coffer config plus the credential writes to perform.
 * Pure — the config is fully built before any side effect runs. A secret value
 * becomes a `credential_refs` entry under an opaque minted ref
 * (`mcp_server/<uuid4 hex>/<key>`, never derived from the name); a plain value
 * stays inline — in `env` for stdio, in `headers` for http (HttpTransport has
 * no `env` field; the parser already gathered an http server's env into
 * `srv.env`).
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

/** Registers the server (with its title, which the create body accepts) and
 *  returns its uid — the handle a rollback and the reach write need. */
async function registerResource(srv: NewServer, config: Record<string, unknown>): Promise<string> {
  const title = srv.title?.trim() || null;
  const { data, error } = await getApiClient().POST("/resources", {
    body: { kind: "mcp_server", name: srv.name, title, config },
  });
  if (error) throwApiError(error, "INTERNAL_ERROR", "register failed");
  if (!data) throw new ApiError("INTERNAL_ERROR", "empty register response");
  return data.uid;
}

/** Writes one secret. `true` when the daemon answered 202: the value is
 *  stored sealed and waits for approval in the Coffer app. */
async function writeCredential(ref: string, value: string): Promise<boolean> {
  const { data, error } = await getApiClient().POST("/credentials", { body: { ref, value } });
  if (error) throwApiError(error, "INTERNAL_ERROR", "secret write failed");
  return data?.approval !== undefined && data?.approval !== null;
}

/** Best-effort rollback of a just-registered server whose secrets failed, so
 *  nothing is left citing a credential that was never stored. A cleanup error
 *  is logged, not surfaced — the secret failure is what the user acts on. */
async function rollbackResource(uid: string, name: string): Promise<void> {
  try {
    await getApiClient().DELETE("/resources/{uid}", { params: { path: { uid } } });
  } catch (e) {
    console.warn(`[importMcpServers] rollback delete failed for ${name}:`, e);
  }
}

async function applyReach(uid: string, reach: ReachIntent): Promise<void> {
  if (reach.mode === "restricted") {
    await scopeApi.put(uid, { agents: reach.agents });
  } else if (reach.mode === "disabled") {
    const { error } = await getApiClient().POST("/resources/{uid}/disable", {
      params: { path: { uid } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "disable failed");
  }
}

/** One server this import registered: its fixed name and its uid. */
interface ImportedServer {
  name: string;
  uid: string;
}

/** One server that was not added, and why. `nameTaken` marks the daemon's 409,
 *  which the dialog shows under the name field. */
export interface FailedServer {
  name: string;
  message: string;
  nameTaken: boolean;
}

export interface ImportReport {
  created: ImportedServer[];
  failed: FailedServer[];
  /** Created servers one of whose secrets waits for approval. */
  awaitingApproval: string[];
  /** Created servers whose reach could not be written (they reach every agent). */
  reachFailed: string[];
}

export interface ImportMcpServersArgs {
  servers: NewServer[];
  /** What a prior attempt of THIS dialog session already registered — name to
   *  uid, mutated in place — so a retry re-attempts only the failures instead
   *  of re-POSTing the created ones (which would 409). */
  created: Map<string, string>;
  /** Defaults to every agent. */
  reach?: ReachIntent;
  t: TFunction;
}

/** The daemon's 409 for a name another server already has. */
function isNameTaken(err: unknown): boolean {
  return err instanceof ApiError && err.code === "RESOURCE_ALREADY_EXISTS";
}

/**
 * Add a batch, one server at a time: register → write its secrets (a failed
 * write rolls the registration back, so a failed registration never orphans a
 * credential and a failed secret never leaves a server citing nothing) → reach.
 * Never rejects: every server lands in `created` or `failed`.
 */
export async function importMcpServers({
  servers,
  created,
  reach = { mode: "everywhere" },
  t,
}: ImportMcpServersArgs): Promise<ImportReport> {
  const report: ImportReport = { created: [], failed: [], awaitingApproval: [], reachFailed: [] };
  for (const srv of servers) {
    const already = created.get(srv.name);
    if (already !== undefined) {
      report.created.push({ name: srv.name, uid: already });
      continue;
    }
    const { config, secrets } = planServer(srv);
    let uid: string | null = null;
    let waiting = false;
    try {
      uid = await registerResource(srv, config);
      for (const s of secrets) {
        if (await writeCredential(s.ref, s.value)) waiting = true;
      }
    } catch (e) {
      if (uid !== null) await rollbackResource(uid, srv.name);
      report.failed.push({
        name: srv.name,
        message: translateApiError(t, e),
        nameTaken: isNameTaken(e),
      });
      continue;
    }
    created.set(srv.name, uid);
    report.created.push({ name: srv.name, uid });
    if (waiting) report.awaitingApproval.push(srv.name);
    try {
      await applyReach(uid, reach);
    } catch {
      report.reachFailed.push(srv.name);
    }
  }
  return report;
}
