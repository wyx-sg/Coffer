// frontend/src/lib/mcp/serverConfig.ts
//
// One pasted server object -> a ParsedServer. Shared by every reader: JSON
// (`mcpServers` entries or one bare object), `claude mcp add-json`, and Codex
// TOML tables (which `pasteToml.ts` maps onto this same shape first).

import type { ParsedEnvVar, ParsedServer, Unreadable } from "./pasteTypes";
import { unreadable } from "./pasteTypes";
import { envVar, mergeByKey } from "./secretDetection";

export function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** The error keys for one pasted block — `env` and `headers` reject the same
 *  shapes, each under its own message. */
const BLOCK_ERRORS = {
  env: { notObject: "errEnvNotObject", badValue: "errBadEnvValue" },
  headers: { notObject: "errHeadersNotObject", badValue: "errBadHeaderValue" },
} as const;

/**
 * A present-but-non-object block (e.g. a string "API_KEY=secret" or an array)
 * and a non-string member value both reject up front rather than silently
 * dropping the block / coercing via `String()` (which produced
 * `[object Object]`) and corrupting the import.
 */
function parseBlock(
  server: string,
  raw: unknown,
  block: keyof typeof BLOCK_ERRORS,
): ParsedEnvVar[] | Unreadable {
  const errors = BLOCK_ERRORS[block];
  if (raw === undefined) return [];
  if (!isObject(raw)) return unreadable(errors.notObject, { name: server });
  const out: ParsedEnvVar[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value !== "string") return unreadable(errors.badValue, { name: server, key });
    out.push(envVar(key, value));
  }
  return out;
}

function nonEmptyString(v: unknown): v is string {
  return typeof v === "string" && v.trim() !== "";
}

/** The server's URL under any key a client config spells it with (`url`;
 *  Windsurf's `serverUrl`; Gemini CLI's `httpUrl`). */
export function serverUrl(cfg: Record<string, unknown>): string | undefined {
  for (const key of ["url", "serverUrl", "httpUrl"]) {
    if (nonEmptyString(cfg[key])) return cfg[key] as string;
  }
  return undefined;
}

/** Whether `cfg` is one server object rather than a map of them. */
export function looksLikeServer(cfg: Record<string, unknown>): boolean {
  return nonEmptyString(cfg.command) || serverUrl(cfg) !== undefined;
}

/**
 * Read one server object. A `command` makes it stdio; a URL makes it
 * Streamable HTTP — including entries marked `type: "sse"`, since Coffer
 * speaks only Streamable HTTP and most such servers serve both.
 */
export function parseServerConfig(name: string, cfg: unknown): ParsedServer | Unreadable {
  if (!isObject(cfg)) return unreadable("errBadServer", { name });
  const env = parseBlock(name, cfg.env, "env");
  if (!Array.isArray(env)) return env;
  if (nonEmptyString(cfg.command)) {
    const args = Array.isArray(cfg.args) ? cfg.args.map(String) : [];
    return { name, transportType: "stdio", command: cfg.command, args, url: "", env };
  }
  const url = serverUrl(cfg);
  if (url !== undefined) {
    // The standard block for an HTTP server carries `headers`; they go
    // through the same secret review as env does.
    const headers = parseBlock(name, cfg.headers, "headers");
    if (!Array.isArray(headers)) return headers;
    const merged = mergeByKey(env, headers);
    return { name, transportType: "http", command: "", args: [], url, env: merged };
  }
  return unreadable("errBadServer", { name });
}
