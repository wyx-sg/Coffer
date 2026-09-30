// frontend/src/lib/mcp/pasteToml.ts
//
// The TOML reader of the paste box: Codex's `[mcp_servers.<name>]` tables
// (`~/.codex/config.toml`), one or many, mapped onto the JSON server shape
// and read by the same `parseServerConfig`.

import type { ParsedServer, PasteResult } from "./pasteTypes";
import { unreadable } from "./pasteTypes";
import { envVar } from "./secretDetection";
import { isObject, parseServerConfig } from "./serverConfig";
import { parseToml, type TomlTable } from "./tomlSubset";

/** Whether `text` carries a Codex MCP server table header. */
export function looksLikeCodexToml(text: string): boolean {
  return /^\s*\[\s*mcp_servers\s*[.\]]/m.test(text);
}

/**
 * Codex's `bearer_token_env_var = "X"` tells Codex to send `Authorization:
 * Bearer $X` from its own environment. Coffer has no such environment to read,
 * and inventing a `Bearer ${X}` placeholder would register a literal that is
 * never expanded. So the least surprising mapping is an `Authorization`
 * header marked secret with an EMPTY value: the review shows the header the
 * server needs, and the user supplies the token (as `Bearer <token>`) there.
 */
function bearerHeader(table: TomlTable): { key: string; value: string; isSecret: true } | null {
  return typeof table.bearer_token_env_var === "string"
    ? { ...envVar("Authorization", ""), isSecret: true }
    : null;
}

/** One Codex table in the JSON server shape: `http_headers` and `headers`
 *  both become `headers` (the latter winning a clash). */
function toServerConfig(table: TomlTable): Record<string, unknown> {
  const { http_headers, headers, ...rest } = table;
  if (http_headers === undefined && headers === undefined) return rest;
  if (http_headers !== undefined && !isObject(http_headers))
    return { ...rest, headers: http_headers };
  if (headers !== undefined && !isObject(headers)) return { ...rest, headers };
  return { ...rest, headers: { ...(http_headers as object), ...(headers as object) } };
}

/** Read pasted Codex TOML (already known to carry an `[mcp_servers…]` header). */
export function parseTomlPaste(text: string): PasteResult {
  const doc = parseToml(text);
  if (!doc.ok) {
    return unreadable("errInvalidToml", { line: String(doc.line), detail: doc.detail });
  }
  const tables = doc.value.mcp_servers;
  if (!isObject(tables)) return unreadable("errServersNotObject", { key: "mcp_servers" });
  const entries = Object.entries(tables);
  if (entries.length === 0) return unreadable("errNoServers");

  const servers: ParsedServer[] = [];
  for (const [name, table] of entries) {
    if (!isObject(table)) return unreadable("errBadServer", { name });
    const parsed = parseServerConfig(name, toServerConfig(table as TomlTable));
    if ("kind" in parsed) return parsed;
    const bearer = bearerHeader(table as TomlTable);
    if (
      bearer &&
      parsed.transportType === "http" &&
      !parsed.env.some((e) => e.key === "Authorization")
    ) {
      parsed.env = [...parsed.env, bearer];
    }
    servers.push(parsed);
  }
  return { kind: "servers", source: "toml", servers };
}
