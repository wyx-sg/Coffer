// frontend/src/kinds/mcp/jsonImport.ts
//
// Parser for pasted MCP server JSON — the standard Claude Desktop /
// Cursor `{"mcpServers": {...}}` shape. Pure (no React, no network).

/** Env var names whose value Coffer treats as a secret by default. */
const SECRET_NAME_RE = /token|secret|pass|pwd|key|cred|auth/i;

export interface ParsedEnvVar {
  key: string;
  value: string;
  /** Heuristic default — the user confirms/flips this in the review step. */
  isSecret: boolean;
}

export interface ParsedServer {
  name: string;
  transportType: "stdio" | "http";
  command: string;
  args: string[];
  url: string;
  env: ParsedEnvVar[];
}

export type ParseResult =
  | { ok: true; servers: ParsedServer[] }
  | { ok: false; errorKey: string; errorParams?: Record<string, string> };

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Returned by `parseEnv` to signal that an env value wasn't a string —
 * coercing via `String()` produced `[object Object]` for objects /
 * arrays, which silently corrupted the import. Reject up front instead.
 */
type EnvParseResult = { ok: true; env: ParsedEnvVar[] } | { ok: false; badKey: string };

function parseEnv(raw: unknown): EnvParseResult {
  if (raw === undefined) return { ok: true, env: [] };
  if (!isObject(raw)) return { ok: true, env: [] };
  const env: ParsedEnvVar[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value !== "string") return { ok: false, badKey: key };
    env.push({ key, value, isSecret: SECRET_NAME_RE.test(key) });
  }
  return { ok: true, env };
}

function parseServer(
  name: string,
  cfg: unknown,
): ParsedServer | { error: true; errorKey?: string; errorParams?: Record<string, string> } {
  if (!isObject(cfg)) return { error: true };
  const envResult = parseEnv(cfg.env);
  if (!envResult.ok) {
    return {
      error: true,
      errorKey: "errBadEnvValue",
      errorParams: { name, key: envResult.badKey },
    };
  }
  const env = envResult.env;
  if (typeof cfg.command === "string" && cfg.command.trim() !== "") {
    return {
      name,
      transportType: "stdio",
      command: cfg.command,
      args: Array.isArray(cfg.args) ? cfg.args.map(String) : [],
      url: "",
      env,
    };
  }
  if (typeof cfg.url === "string" && cfg.url.trim() !== "") {
    return { name, transportType: "http", command: "", args: [], url: cfg.url, env };
  }
  return { error: true };
}

/**
 * Parse pasted MCP server JSON. Accepts the standard
 * `{"mcpServers": {"<name>": {...}}}` shape and a bare `{"<name>": {...}}`
 * map; returns every server found (the import is a batch).
 */
export function parseMcpJson(text: string): ParseResult {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return { ok: false, errorKey: "errInvalidJson" };
  }
  if (!isObject(raw)) return { ok: false, errorKey: "errNoServers" };

  // A bare, name-less config gives no server name — nudge to the wrapped form.
  if (!isObject(raw.mcpServers) && ("command" in raw || "url" in raw)) {
    return { ok: false, errorKey: "errNoServers" };
  }

  const map = isObject(raw.mcpServers) ? raw.mcpServers : raw;
  const entries = Object.entries(map);
  if (entries.length === 0) return { ok: false, errorKey: "errNoServers" };

  const servers: ParsedServer[] = [];
  for (const [name, cfg] of entries) {
    const parsed = parseServer(name, cfg);
    if ("error" in parsed) {
      return {
        ok: false,
        errorKey: parsed.errorKey ?? "errBadServer",
        errorParams: parsed.errorParams ?? { name },
      };
    }
    servers.push(parsed);
  }
  return { ok: true, servers };
}
