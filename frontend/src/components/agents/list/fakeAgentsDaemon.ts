// src/components/agents/list/fakeAgentsDaemon.ts — test-only: an in-memory daemon behind the typed client.
//
// The Agents list, its dialogs and the connection change read a dozen routes;
// tests mock only the network boundary and let the real hooks run against
// this fake, which keeps registrations and connections as the daemon would.
import type { AgentProviderInfo } from "@/lib/api/agentProviders";
import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";

interface FakeCall {
  method: string;
  path: string;
  body?: unknown;
}

export interface FakeDaemon {
  types: AgentTypeOut[];
  /** The managed agents a conversation (and so Ask an agent) can run on. */
  providers: AgentProviderInfo[];
  connections: Record<string, CofferConnection>;
  /** The model binding on an agent's record, by uid. */
  models: Record<string, string>;
  /** Uids of agents running on a Coffer connection (the rest are on their own login). */
  onConnection: string[];
  /** The agent's own catalogue per type key (its order is the CLI's, not a default). */
  catalogue: Record<string, string[]>;
  /** The default model each agent's own config names, per type key; absent → the agent chooses. */
  nativeDefaults: Record<string, string>;
  calls: FakeCall[];
  /** Subfolder names per absolute path, for the folder browse. */
  folders: Record<string, string[]>;
  /** What the native folder dialog answers. */
  pick: { available: boolean; path: string | null };
  /** Uids of agents switched off. */
  disabled: string[];
  /** Registrations so far; the next uid is `agt_<seq + 1>`. */
  seq: number;
  /** Return an ApiError to make that request fail. */
  fail?: (call: FakeCall) => ApiError | undefined;
  /** Return a promise to hold that request until it settles (a slow write). */
  hold?: (call: FakeCall) => Promise<void> | undefined;
}

export function typeRow(over: Partial<AgentTypeOut> & Pick<AgentTypeOut, "type">): AgentTypeOut {
  const dir = over.type === "codex" ? "/Users/me/.codex" : "/Users/me/.claude";
  return {
    addable: true,
    config_dir: dir,
    default_skill_dir: `${dir}/skills`,
    display_name: over.type === "codex" ? "Codex" : "Claude Code",
    name: over.type === "codex" ? "codex" : "claude-code",
    other_config_dir: null,
    standard_config_dir: dir,
    state: "installed_active",
    uid: null,
    version: over.type === "codex" ? "0.41.0" : "2.1.281",
    install_handoff: null,
    install_url: "",
    ...over,
  };
}

export function fakeDaemon(init: Partial<FakeDaemon> = {}): FakeDaemon {
  return {
    types: [],
    providers: [],
    connections: {},
    models: {},
    onConnection: [],
    catalogue: {},
    nativeDefaults: {},
    calls: [],
    folders: {},
    pick: { available: true, path: null },
    disabled: [],
    seq: 0,
    ...init,
  };
}

function parts(installed: boolean) {
  return ["mcp", "memory_hook"].map((key) => ({
    key,
    installed,
    detail: installed ? `/bin/${key}` : null,
  }));
}

function connected(d: FakeDaemon, uid: string, on: boolean): CofferConnection {
  const next: CofferConnection = {
    state: on ? "connected" : "disconnected",
    parts: parts(on),
  };
  d.connections[uid] = next;
  return next;
}

/** The request handler for `fakeApi()`: routes each request to the fake's state. */
export function fakeCallFor(d: FakeDaemon) {
  return async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    const method = opts.method ?? "GET";
    const req = { method, path, body: opts.body };
    d.calls.push(req);
    const failure = d.fail?.(req);
    if (failure) throw failure;
    await d.hold?.(req);
    if (path === "/daemon/status") return { features: {} };
    const resource = path.match(/^\/resources\/([^/?]+)(?:\/(enable|disable))?$/);
    if (resource) {
      const uid = decodeURIComponent(resource[1]);
      if (resource[2] === "enable") d.disabled = d.disabled.filter((u) => u !== uid);
      if (resource[2] === "disable") d.disabled.push(uid);
      return { uid, enabled: !d.disabled.includes(uid) };
    }
    if (path === "/fs/pick-folder") return d.pick;
    if (path.startsWith("/fs/browse")) {
      const at = decodeURIComponent(path.split("?path=")[1] ?? "");
      const names = d.folders[at];
      if (!names) throw new ApiError("FS_NOT_FOUND", "no such folder");
      return {
        path: at,
        parent: null,
        entries: names.map((name) => ({ name, path: `${at}/${name}` })),
      };
    }
    const conn = path.match(/^\/agents\/([^/]+)\/coffer-connection$/);
    if (conn) {
      const uid = decodeURIComponent(conn[1]);
      if (method === "POST") return connected(d, uid, true);
      if (method === "DELETE") return connected(d, uid, false);
      return d.connections[uid] ?? { state: "disconnected", parts: parts(false) };
    }
    if (path === "/agents/types") return { types: d.types, install_handoff: null };
    if (path === "/agent-providers") return { agents: d.providers };
    const catalogue = path.match(/^\/agent-providers\/([^/]+)\/models$/);
    if (catalogue) {
      const ids = d.catalogue[decodeURIComponent(catalogue[1])] ?? [];
      return {
        models: ids.map((id) => ({ id, name: id, efforts: [] })),
        default_model: d.nativeDefaults[decodeURIComponent(catalogue[1])] ?? null,
      };
    }
    if (path === "/agents" && method === "POST") {
      const body = opts.body as { type: string; config_dir?: string };
      const row = d.types.find((r) => r.type === body.type)!;
      row.uid = `agt_${++d.seq}`;
      if (body.config_dir) row.config_dir = body.config_dir;
      return { ...row, uid: row.uid };
    }
    const one = path.match(/^\/agents\/([^/?]+)$/);
    if (one) {
      const uid = decodeURIComponent(one[1]);
      const row = d.types.find((r) => r.uid === uid);
      if (method === "DELETE" && row) row.uid = null;
      if (method === "PATCH" && row) Object.assign(row, opts.body);
      return row
        ? {
            ...row,
            model: d.models[uid] ?? null,
            connection_uid: d.onConnection.includes(uid) ? "conn_1" : null,
          }
        : undefined;
    }
    if (path.endsWith("/hooks")) return { coffer_hook: null, items: [], parse_errors: [] };
    // Every list a count reads: nothing in it.
    return { items: [], total: 0, candidates: [], resources: [] };
  };
}
