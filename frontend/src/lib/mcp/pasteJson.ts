// frontend/src/lib/mcp/pasteJson.ts
//
// The JSON reader of the paste box: an `mcpServers` block (also VS Code's
// `servers` and `mcp_servers`), a bare `{"<name>": {...}}` map, or one server
// object whose name is suggested from its package or host.

import type { ParsedServer, PasteResult } from "./pasteTypes";
import { unreadable } from "./pasteTypes";
import { isObject, looksLikeServer, parseServerConfig, serverUrl } from "./serverConfig";
import { nameFromCommand, nameFromUrl } from "./serverNames";

const WRAPPER_KEYS = ["mcpServers", "servers", "mcp_servers"];

/** Line / column (1-based) of `position` in `text`. */
function lineColumn(text: string, position: number): { line: number; column: number } {
  const before = text.slice(0, position);
  const line = before.split("\n").length;
  return { line, column: position - before.lastIndexOf("\n") };
}

/**
 * `JSON.parse`'s complaint as i18n params. V8 says "… in JSON at position N"
 * (newer versions add "(line L column C)"); Firefox says "at line L column C";
 * WebKit gives no location, which gets `errInvalidJsonNoLocation`.
 */
export function jsonSyntaxError(text: string, error: unknown): PasteResult {
  const message = error instanceof Error ? error.message : String(error);
  const lc = /line (\d+) column (\d+)/.exec(message);
  const pos = /at position (\d+)/.exec(message);
  const detail = message
    .replace(/^JSON(?:\.parse)?(?: Parse error)?:\s*/i, "")
    .replace(/\s*(?:in JSON\s*)?at (?:position \d+|line \d+ column \d+)[^]*$/, "")
    .replace(/\s*\(line \d+ column \d+\)$/, "")
    .replace(/ of the JSON data$/, "")
    .trim();
  if (lc) return unreadable("errInvalidJson", { line: lc[1], column: lc[2], detail });
  if (pos) {
    const { line, column } = lineColumn(text, Number(pos[1]));
    return unreadable("errInvalidJson", { line: String(line), column: String(column), detail });
  }
  return unreadable("errInvalidJsonNoLocation", { detail });
}

function servers(list: ParsedServer[]): PasteResult {
  return { kind: "servers", source: "json", servers: list };
}

/** Read pasted JSON (already known to start with `{` or `[`). */
export function parseJsonPaste(text: string): PasteResult {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (error) {
    return jsonSyntaxError(text, error);
  }
  if (!isObject(raw)) return unreadable("errNotAnObject");

  const wrapper = WRAPPER_KEYS.find((k) => k in raw);
  if (wrapper !== undefined && !isObject(raw[wrapper])) {
    return unreadable("errServersNotObject", { key: wrapper });
  }
  if (wrapper === undefined && looksLikeServer(raw)) {
    const url = serverUrl(raw);
    const name =
      typeof raw.command === "string"
        ? nameFromCommand(raw.command, Array.isArray(raw.args) ? raw.args.map(String) : [])
        : nameFromUrl(url ?? "");
    const one = parseServerConfig(name, raw);
    return "kind" in one ? one : servers([one]);
  }

  const map = wrapper === undefined ? raw : (raw[wrapper] as Record<string, unknown>);
  const entries = Object.entries(map);
  if (entries.length === 0) return unreadable("errNoServers");
  const out: ParsedServer[] = [];
  for (const [name, cfg] of entries) {
    const parsed = parseServerConfig(name, cfg);
    if ("kind" in parsed) return parsed;
    out.push(parsed);
  }
  return servers(out);
}
