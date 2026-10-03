// frontend/src/lib/mcp/pasteParse.ts
//
// The Add server paste box's one entry point (spec web-ui "Add MCP servers
// from one paste box" / "Explain unreadable pasted input in the dialog").
// Recognises, first fit wins: JSON, Codex TOML, a URL, a command line.
// Pure — no React, no network; the dialog renders what this returns.

import { parseCommandPaste } from "./pasteCommand";
import { parseJsonPaste } from "./pasteJson";
import { looksLikeCodexToml, parseTomlPaste } from "./pasteToml";
import type { ParsedServer, PasteResult, PasteSource } from "./pasteTypes";
import { unreadable } from "./pasteTypes";
import { finaliseNames, nameFromUrl } from "./serverNames";

export type { ParsedServer, PasteResult } from "./pasteTypes";
export { MCP_SERVER_NAME_MAX, isValidServerName, serverNameTooLong } from "./serverNames";

/**
 * One URL on its own. Credentials in its query (`?token=`, `?api_key=`) are
 * kept as pasted: the URL is what the server answers on, and the dialog may
 * warn about them rather than the parser silently changing the address.
 */
function parseUrlPaste(text: string): PasteResult | null {
  if (!/^https?:\/\/\S+$/i.test(text)) return null;
  try {
    new URL(text);
  } catch {
    return null;
  }
  const server: ParsedServer = {
    name: nameFromUrl(text),
    transportType: "http",
    command: "",
    args: [],
    url: text,
    env: [],
  };
  return { kind: "servers", source: "url", servers: [server] };
}

function recognise(text: string): PasteResult {
  if (text.startsWith("{")) return parseJsonPaste(text);
  if (looksLikeCodexToml(text)) return parseTomlPaste(text);
  if (text.startsWith("[")) return parseJsonPaste(text);
  return parseUrlPaste(text) ?? parseCommandPaste(text) ?? unreadable("errUnreadable");
}

/**
 * Read whatever was pasted into servers, or explain why not. Every server's
 * name is normalised to the pattern the daemon registers (with
 * `originalName` set when that changed it) and de-duplicated within the paste.
 */
export function parsePaste(text: string): PasteResult {
  const trimmed = text.trim();
  if (trimmed === "") return { kind: "empty" };
  const result = recognise(trimmed);
  return result.kind === "servers" ? { ...result, servers: finaliseNames(result.servers) } : result;
}

/** The i18n key of the source summary, relative to `mcp.paste`. */
const SUMMARY_KEYS: Record<PasteSource, string> = {
  json: "foundJson",
  toml: "foundToml",
  command: "foundCommand",
  url: "foundUrl",
};

/**
 * The one line the dialog shows under the box for `result`: its i18n key
 * relative to `mcp.paste`, and the interpolation values. `null` for an empty
 * box. An unreadable result's line is its specific error message.
 */
export function describePaste(
  result: PasteResult,
): { key: string; params: Record<string, string | number> } | null {
  if (result.kind === "empty") return null;
  if (result.kind === "unreadable")
    return { key: result.errorKey, params: result.errorParams ?? {} };
  const names = result.servers.map((s) => s.name).join(", ");
  return { key: SUMMARY_KEYS[result.source], params: { count: result.servers.length, names } };
}
