// frontend/src/lib/mcp/pasteTypes.ts
//
// The shapes the Add server paste box reads into. Kept apart from the parsers
// so each reader (JSON, TOML, command line, URL) can import them without an
// import cycle through `pasteParse.ts`, which re-exports them.

export interface ParsedEnvVar {
  key: string;
  value: string;
  /** Heuristic default — the user confirms/flips this in the review step. */
  isSecret: boolean;
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
