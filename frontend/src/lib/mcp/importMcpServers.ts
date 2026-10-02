// frontend/src/lib/mcp/importMcpServers.ts
// The plumbing behind "Add MCP server": turn each parsed server into a Coffer
// config plus secret writes, store its secrets first (registration probes the
// refs it cites, and a secret supplied for a destination is approved with the
// registration), register it (removing the just-written secrets when that
// fails), then give it its reach.
// Pure functions + one async batch, so the dialog stays a view and the
// mutation hook (useMcpServerMutations.ts) stays one line.
import type { TFunction } from "i18next";

import { ApiError, translateApiError } from "@/lib/api/errors";
import { resourcesApi } from "@/lib/api/resources";
import { secretsApi } from "@/lib/api/secret";
import { scopeApi } from "@/lib/api/scope";
import { writeSecret } from "@/lib/secretWrite";
import { mintSecretRef } from "@/lib/secretRef";
import type { ParsedServer } from "@/lib/mcp/pasteParse";

/** One server as the dialog confirmed it: the parsed shape plus the note
 *  and working directory the form may carry (`""` = none). */
export interface NewServer extends ParsedServer {
  description?: string;
  /** stdio only: the folder the command starts in. */
  cwd?: string;
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
 *  any is empty, so an empty secret never reaches the secret store. */
export function missingSecretValues(srv: ParsedServer): string[] {
  return srv.env.filter((e) => e.isSecret && e.value === "" && !e.ref).map((e) => e.key);
}

/**
 * A parsed server as a Coffer config plus the secret writes to perform.
 * Pure — the config is fully built before any side effect runs. A secret value
 * becomes a `secret_refs` entry under an opaque minted ref
 * (`mcp_server/<uuid4 hex>/<key>`, never derived from the name); a plain value
 * stays inline — in `env` for stdio, in `headers` for http (HttpTransport has
 * no `env` field; the parser already gathered an http server's env into
 * `srv.env`).
 */
function planServer(srv: NewServer): ServerPlan {
  const secretRefs: Record<string, string> = {};
  const plain: Record<string, string> = {};
  const secrets: { ref: string; value: string }[] = [];
  for (const e of srv.env) {
    if (e.isSecret && e.ref) {
      // A stored secret picked for this row: cite it, write nothing.
      secretRefs[e.key] = e.ref;
    } else if (e.isSecret) {
      const ref = mintSecretRef("mcp_server", e.key);
      secretRefs[e.key] = ref;
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
          secret_refs: secretRefs,
          ...(srv.cwd?.trim() ? { cwd: srv.cwd.trim() } : {}),
        }
      : { type: "http", url: srv.url, headers: plain, secret_refs: secretRefs };
  return { config: { transport }, secrets };
}

/** Registers the server (with its note, which the create body accepts) and
 *  returns its uid — the handle the reach write needs. */
async function registerResource(srv: NewServer, config: Record<string, unknown>): Promise<string> {
  const description = srv.description?.trim() || null;
  const created = await resourcesApi.create({
    kind: "mcp_server",
    name: srv.name,
    description,
    config,
  });
  return created.uid;
}

/** Best-effort rollback of secrets written before a failed registration, so
 *  the store holds nothing that no server cites. A cleanup error is logged, not
 *  surfaced — the registration failure is what the user acts on. */
async function rollbackSecrets(refs: string[], name: string): Promise<void> {
  for (const ref of refs) {
    try {
      await secretsApi.remove(ref);
    } catch (e) {
      console.warn(`[importMcpServers] rollback delete failed for ${name}:`, e);
    }
  }
}

/** Whether the daemon holds a binding for `uid`'s secrets until a person
 *  approves it. A registration that cites an existing secret, or one that is
 *  already in use elsewhere, records the approval with the registration. */
async function hasPendingApproval(uid: string): Promise<boolean> {
  try {
    const { approvals } = await secretsApi.pendingApprovals();
    return approvals.some((a) => a.destination_uid === uid);
  } catch {
    return false;
  }
}

async function applyReach(uid: string, reach: ReachIntent): Promise<void> {
  if (reach.mode === "restricted") {
    await scopeApi.put(uid, { agents: reach.agents });
  } else if (reach.mode === "disabled") {
    await resourcesApi.disable(uid);
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
 * Add a batch, one server at a time: write its secrets → register (a failed
 * registration removes the secrets just written, so it never orphans one, and a
 * server never cites a secret that was not stored) → reach.
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
    let uid: string;
    let waiting = false;
    const written: string[] = [];
    try {
      for (const sec of secrets) {
        if (await writeSecret(sec.ref, sec.value)) waiting = true;
        written.push(sec.ref);
      }
      uid = await registerResource(srv, config);
    } catch (e) {
      await rollbackSecrets(written, srv.name);
      report.failed.push({
        name: srv.name,
        message: translateApiError(t, e),
        nameTaken: isNameTaken(e),
      });
      continue;
    }
    if (!waiting) waiting = await hasPendingApproval(uid);
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
