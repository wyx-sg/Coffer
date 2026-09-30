// frontend/src/lib/mcp/pasteTypes.ts
//
// The shapes the Add server paste box reads into. Kept apart from the parsers
// so each reader (JSON, TOML, command line, URL) can import them without an
// import cycle through `pasteParse.ts`, which re-exports them.

/**
 * One KEY / value row: a stdio server's environment variable or an HTTP
 * server's header. The paste readers fill only the first three fields; the
 * rest are set by the edit dialog's stored-secret picker (`KeyValueRows`).
 */
export interface ParsedEnvVar {
  key: string;
  /** Plain row: the value. Secret row: a value typed for a new or replaced
   *  secret ("" = none typed). */
  value: string;
  /** Heuristic default — the user confirms/flips this in the review step. */
  isSecret: boolean;
  /** Secret row: the stored secret it cites instead of a typed value —
   *  `secret/<name>` (Secrets page) or the server's own minted ref. Null or
   *  absent: `value` is stored as a new secret (or, with `storedRef`, written
   *  through it). Ignored on a plain row. */
  ref?: string | null;
  /** Edit only: the ref this row loaded with, so a new value rotates through it. */
  storedRef?: string | null;
  /** Edit only: the key this row loaded with (a renamed key cannot keep its
   *  own stored secret without a new value). */
  loadedKey?: string | null;
}

export interface ParsedServer {
  /** Normalised to the pattern mcp-gateway registers (see `serverNames.ts`). */
  name: string;
  /** The name as the paste spelled it, when normalising changed it. */
  originalName?: string;
  transportType: "stdio" | "http";
  command: string;
  args: string[];
  url: string;
  /**
   * The key/value pairs the review step shows with a Secret toggle. For stdio
   * these are the `env` block. For http they are what the server is sent as
   * headers: the `headers` block, plus any `env` block (HTTP has no env, so
   * those values travel as headers too); a `headers` entry wins a key clash.
   */
  env: ParsedEnvVar[];
}

export type PasteSource = "json" | "toml" | "command" | "url";

/**
 * What the paste box made of its input. `errorKey` is relative to the
 * `mcp.paste` i18n namespace; `errorParams` are its interpolation values.
 */
export type PasteResult =
  | { kind: "empty" }
  | { kind: "servers"; source: PasteSource; servers: ParsedServer[] }
  | { kind: "unreadable"; errorKey: string; errorParams?: Record<string, string> };

/** The unreadable arm, for readers that return either servers or an error. */
export type Unreadable = Extract<PasteResult, { kind: "unreadable" }>;

export function unreadable(errorKey: string, errorParams?: Record<string, string>): Unreadable {
  return errorParams
    ? { kind: "unreadable", errorKey, errorParams }
    : { kind: "unreadable", errorKey };
}
