// frontend/src/lib/mcp/importMcpServers.ts
// The plumbing behind "Add MCP server": turn each server into a Coffer config,
// store its new secrets first (registration probes the refs it cites, and a
// secret supplied for a destination is approved with the registration),
// register it (removing the just-written secrets when that fails), then give it
// its reach. A chosen secret is cited as `secret_refs[KEY] = secret/<name>`.
// Pure functions + one async batch, so the dialog stays a view and the
// mutation hook (useMcpServerMutations.ts) stays one line.
import type { TFunction } from "i18next";

import { persistNewSecrets, secretRef, type KeyValueSecretRow } from "@/lib/secretValue";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { withInlineApproval } from "@/lib/inlineApproval";
import { resourcesApi } from "@/lib/api/resources";
import { secretsApi } from "@/lib/api/secret";
import { scopeApi } from "@/lib/api/scope";
import type { ParsedServer } from "@/lib/mcp/pasteParse";
import {
  authSchemesField,
  missingSecretKeys,
  plainMapOfRows,
  secretRefsOfRows,
} from "@/lib/mcp/serverRows";

/** One server as the dialog confirmed it: the parsed shape with its rows as the
 *  form holds them, plus the note and working directory the form may carry
 *  (`""` = none). */
export interface NewServer extends Omit<ParsedServer, "env"> {
  env: KeyValueSecretRow[];
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

/** The keys of `srv` whose new secret is still without a value — a
 *  `bearer_token_env_var` header arrives that way. The dialog asks for them;
 *  nothing is sent while any is empty, so an empty secret never reaches the
 *  secret store. */
export const missingSecretValues = (srv: Pick<NewServer, "env">): string[] =>
  missingSecretKeys(srv.env);

/**
 * A server as a Coffer config. Pure — built before any side effect runs. A
 * plain value stays inline — in `env` for stdio, in `headers` for http
 * (HttpTransport has no `env` field); a secret becomes a `secret_refs` entry.
 */
function configOf(srv: NewServer): Record<string, unknown> {
  const plain = plainMapOfRows(srv.env);
  const secretRefs = secretRefsOfRows(srv.env);
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
      : {
          type: "http",
          url: srv.url,
          headers: plain,
          secret_refs: secretRefs,
          ...authSchemesField(srv.env),
        };
  return { transport };
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

/** The refs whose binding to server `uid` waits for a person to approve it, or
 *  null when none does. A registration that cites an existing secret records
 *  the pending `bind` approval with the registration. */
async function pendingRefsFor(uid: string): Promise<string[] | null> {
  try {
    const { approvals } = await secretsApi.pendingApprovals();
    const mine = approvals.filter((a) => a.op === "bind" && a.destination_uid === uid);
    return mine.length > 0 ? mine.map((a) => a.ref ?? "") : null;
  } catch {
    return null;
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
  /** Created servers whose secret goes to a new place and waits for approval,
   *  with the environment variable / header each waiting secret is for. */
  awaitingApproval: { name: string; secrets: string[] }[];
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
export async function importMcpServers(args: ImportMcpServersArgs): Promise<ImportReport> {
  // In the desktop app, what the batch left waiting is approved under one
  // presence check at the end (`lib/inlineApproval`); what is still waiting
  // after that — a cancelled check, or a browser — is reported as before.
  const report = await withInlineApproval(
    () => registerAll(args),
    (r) => (r.awaitingApproval.length > 0 ? r.created.map((c) => c.uid) : null),
  );
  if (report.awaitingApproval.length === 0) return report;
  const uidOf = new Map(report.created.map((c) => [c.name, c.uid]));
  const still: ImportReport["awaitingApproval"] = [];
  for (const entry of report.awaitingApproval) {
    const uid = uidOf.get(entry.name);
    if (uid === undefined || (await pendingRefsFor(uid)) !== null) still.push(entry);
  }
  return { ...report, awaitingApproval: still };
}

async function registerAll({
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
    const config = configOf(srv);
    let uid: string;
    const written: string[] = [];
    try {
      for (const row of srv.env) {
        if (row.value.kind !== "new" || row.key.trim() === "") continue;
        written.push(secretRef(row.value.name));
        await persistNewSecrets([row.value]);
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
    const refs = await pendingRefsFor(uid);
    if (refs) {
      const keyed = srv.env.filter(
        (r) => r.value.kind !== "plain" && refs.includes(secretRef(r.value.name)),
      );
      const every = srv.env.filter((r) => r.value.kind !== "plain");
      report.awaitingApproval.push({
        name: srv.name,
        secrets: (keyed.length > 0 ? keyed : every).map((r) => r.key.trim()),
      });
    }
    created.set(srv.name, uid);
    report.created.push({ name: srv.name, uid });
    try {
      await applyReach(uid, reach);
    } catch {
      report.reachFailed.push(srv.name);
    }
  }
  return report;
}
