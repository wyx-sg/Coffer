// frontend/src/kinds/mcp/jsonImport.ts
//
// Parser for pasted MCP server JSON — the standard Claude Desktop /
// Cursor `{"mcpServers": {...}}` shape. Pure (no React, no network).

/** Env var names whose value Coffer treats as a secret by default. */
const SECRET_NAME_RE = /token|secret|pass|pwd|key|cred|auth/i;

/**
 * Values that *look* like a secret regardless of the var name. Mirrors the
 * backend's `_SECRET_PATTERNS` (server_config.py) so a secret-valued var
 * with an innocuous name (e.g. `SLACK_URL: "Bearer xoxb-…"`) is steered into
 * the keychain in the review step instead of being POSTed inline and
 * rejected with a CONFIG_INVALID the user can't easily action.
 */
const SECRET_VALUE_RE = /^(?:Bearer\s+|ghp_|gho_|github_pat_|sk-|xox[abp]-|eyJ[A-Za-z0-9_-]{20,})/;

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
 * Returned by `parseEnv`. A present-but-non-object `env` (e.g. a string
 * "API_KEY=secret" or an array) and a non-string member value both reject
 * up front rather than silently dropping the env block / coercing via
 * `String()` (which produced `[object Object]`) and corrupting the import.
 */
type EnvParseResult =
  | { ok: true; env: ParsedEnvVar[] }
  | { ok: false; errorKey: "errEnvNotObject" }
  | { ok: false; errorKey: "errBadEnvValue"; badKey: string };

function parseEnv(raw: unknown): EnvParseResult {
  if (raw === undefined) return { ok: true, env: [] };
  if (!isObject(raw)) return { ok: false, errorKey: "errEnvNotObject" };
  const env: ParsedEnvVar[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value !== "string") return { ok: false, errorKey: "errBadEnvValue", badKey: key };
    env.push({ key, value, isSecret: SECRET_NAME_RE.test(key) || SECRET_VALUE_RE.test(value) });
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
      errorKey: envResult.errorKey,
      errorParams:
        envResult.errorKey === "errBadEnvValue" ? { name, key: envResult.badKey } : { name },
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
