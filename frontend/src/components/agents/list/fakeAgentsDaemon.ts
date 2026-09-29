// src/components/agents/list/fakeAgentsDaemon.ts — test-only: an in-memory daemon behind `call` and `getApiClient`.
//
// The Agents list, its dialogs and the connection change read a dozen routes;
// tests mock only the network boundary and let the real hooks run against
// this fake, which keeps registrations and connections as the daemon would.
import { vi } from "vitest";

import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";

interface FakeCall {
  method: string;
  path: string;
  body?: unknown;
}

export interface FakeDaemon {
  types: AgentTypeOut[];
  connections: Record<string, CofferConnection>;
  models: Record<string, string>;
  memoryOn: boolean;
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
    ...over,
  };
}

export function fakeDaemon(init: Partial<FakeDaemon> = {}): FakeDaemon {
  return {
    types: [],
    connections: {},
    models: {},
    memoryOn: true,
    calls: [],
    folders: {},
    pick: { available: true, path: null },
    disabled: [],
    seq: 0,
    ...init,
  };
}

function parts(d: FakeDaemon, installed: boolean) {
  const keys = d.memoryOn ? ["mcp", "memory_hook"] : ["mcp"];
  return keys.map((key) => ({ key, installed, detail: installed ? `/bin/${key}` : null }));
}

function connected(d: FakeDaemon, uid: string, on: boolean): CofferConnection {
  const next: CofferConnection = {
    state: on ? "connected" : "disconnected",
    parts: parts(d, on),
  };
  d.connections[uid] = next;
  return next;
}

/** The `call` stand-in: routes each request to the fake's state. */
export function fakeCallFor(d: FakeDaemon) {
  return vi.fn(async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    const method = opts.method ?? "GET";
    const req = { method, path, body: opts.body };
    d.calls.push(req);
    const failure = d.fail?.(req);
    if (failure) throw failure;
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
      return d.connections[uid] ?? { state: "disconnected", parts: parts(d, false) };
    }
    if (path === "/agents/types") return { types: d.types };
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
      return row ? { ...row, model: d.models[uid] ?? null } : undefined;
    }
    if (path.endsWith("/hooks")) return { coffer_hook: null, items: [], parse_errors: [] };
    // Every list a count reads: nothing in it.
    return { items: [], total: 0, candidates: [] };
  });
}

/** The `getApiClient()` stand-in: resources (enabled flags) and daemon status. */
export function fakeClientFor(d: FakeDaemon) {
  const ok = (data: unknown) => Promise.resolve({ data, error: undefined });
  return {
    GET: vi.fn((path: string, init?: { params?: { path?: { uid?: string } } }) => {
      if (path === "/daemon/status") return ok({ features: { memory: d.memoryOn } });
      if (path === "/resources/{uid}") {
        const uid = init?.params?.path?.uid ?? "";
        return ok({ uid, enabled: !d.disabled.includes(uid) });
      }
      return ok({ resources: [] });
    }),
    POST: vi.fn((path: string, init?: { params?: { path?: { uid?: string } } }) => {
      const uid = init?.params?.path?.uid ?? "";
      d.calls.push({ method: "POST", path: path.replace("{uid}", uid) });
      if (path === "/resources/{uid}/enable") d.disabled = d.disabled.filter((u) => u !== uid);
      if (path === "/resources/{uid}/disable") d.disabled.push(uid);
      return ok(undefined);
    }),
    PATCH: vi.fn(() => ok(undefined)),
    DELETE: vi.fn(() => ok(undefined)),
  };
}
