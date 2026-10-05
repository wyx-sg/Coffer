// frontend/src/lib/mcp/pasteCommand.ts
//
// The command-line reader of the paste box: `claude mcp add …`,
// `claude mcp add-json …`, `codex mcp add …`, or a plain command such as
// `npx -y @modelcontextprotocol/server-github` (leading `KEY=value`
// assignments become its environment). Returns `null` when the line is not a
// command at all, so the caller can say it could not read it.

import { jsonSyntaxError } from "./pasteJson";
import type { ParsedEnvVar, ParsedServer, PasteResult, Unreadable } from "./pasteTypes";
import { unreadable } from "./pasteTypes";
import { envVar, mergeByKey, withHeaderSchemes } from "./secretDetection";
import { parseServerConfig } from "./serverConfig";
import { nameFromCommand } from "./serverNames";
import { ASSIGNMENT_RE, looksLikeProgram, looksLikeProse } from "./commandLine";
import { shellSplit } from "./shellTokens";

/** A header argument `Name: value` (but not a URL's `https://`). */
const HEADER_RE = /^[A-Za-z0-9_-]+:(?!\/\/)/;

type FlagKind = "env" | "header" | "transport" | "url" | "bearer" | "value";

/** `claude mcp add` options; `-e` and `-H` take one or more values. */
const CLAUDE_FLAGS: Record<string, FlagKind> = {
  ...{ "-e": "env", "--env": "env", "-H": "header", "--header": "header" },
  ...{ "-t": "transport", "--transport": "transport", "-s": "value", "--scope": "value" },
  ...{ "--client-id": "value", "--callback-port": "value" },
};
/** `codex mcp add` options; `--env` is repeated, one value each. */
const CODEX_FLAGS: Record<string, FlagKind> = {
  "--env": "env",
  "--url": "url",
  "--bearer-token-env-var": "bearer",
};

interface Args {
  env: ParsedEnvVar[];
  headers: ParsedEnvVar[];
  transport: string;
  url?: string;
  bearer?: string;
  /** Positionals before `--` / before the command: the server name first. */
  positionals: string[];
  /** The command and its arguments (after `--`, or from the second positional). */
  rest: string[];
}

function pair(raw: string, sep: "=" | ":"): ParsedEnvVar {
  const at = raw.indexOf(sep);
  return envVar(raw.slice(0, at).trim(), raw.slice(at + 1).trim());
}

/** Read the options and positionals after `… mcp add`. */
function readArgs(
  words: string[],
  flags: Record<string, FlagKind>,
  variadic: boolean,
): Args | Unreadable {
  const out: Args = { env: [], headers: [], transport: "stdio", positionals: [], rest: [] };
  for (let i = 0; i < words.length; i++) {
    const word = words[i];
    if (word === "--") {
      out.rest = words.slice(i + 1);
      return out;
    }
    if (out.positionals.length === 2 && out.transport === "stdio") {
      // `claude mcp add name cmd args…` without `--`: the rest is the command's.
      // (An HTTP server's options may follow its URL, so those keep parsing.)
      out.rest = [out.positionals.pop() as string, ...words.slice(i)];
      return out;
    }
    if (!word.startsWith("-") || word === "-") {
      out.positionals.push(word);
      continue;
    }
    const eq = word.indexOf("=");
    const flag = word.startsWith("--") && eq > 0 ? word.slice(0, eq) : word;
    const kind = flags[flag];
    if (kind === undefined) continue; // an option that changes nothing Coffer stores
    const value = flag === word ? words[++i] : word.slice(eq + 1);
    if (value === undefined) return unreadable("errCommandOption", { flag });
    if (kind === "env" || kind === "header") {
      const [re, sep, list] =
        kind === "env"
          ? [ASSIGNMENT_RE, "=" as const, out.env]
          : [HEADER_RE, ":" as const, out.headers];
      if (!re.test(value)) return unreadable("errCommandOption", { flag });
      list.push(pair(value, sep));
      while (variadic && flag === word && re.test(words[i + 1] ?? ""))
        list.push(pair(words[++i], sep));
    } else if (kind === "transport") out.transport = value;
    else if (kind === "url") out.url = value;
    else if (kind === "bearer") out.bearer = value;
  }
  if (out.positionals.length >= 2) out.rest = out.positionals.splice(1);
  return out;
}

/** The server `claude mcp add` / `codex mcp add` describes. */
function fromAdd(tool: string, a: Args): ParsedServer | Unreadable {
  const name = a.positionals[0];
  if (name === undefined) return unreadable("errCommandNoName", { tool });
  const http = a.url !== undefined || a.transport === "http" || a.transport === "sse";
  if (http) {
    const url = a.url ?? a.rest[0];
    if (url === undefined) return unreadable("errCommandNoTarget", { tool });
    // Codex's --bearer-token-env-var names an env var Coffer cannot read; the
    // header is offered empty and secret, under the scheme Bearer, for the user to fill with the
    // token alone (see pasteToml.ts).
    const bearer = a.bearer
      ? [{ ...envVar("Authorization", ""), isSecret: true, scheme: "Bearer" as const }]
      : [];
    const headers = withHeaderSchemes(mergeByKey(a.env, [...bearer, ...a.headers]));
    return { name, transportType: "http", command: "", args: [], url, env: headers };
  }
  const [command, ...args] = a.rest;
  if (command === undefined) return unreadable("errCommandNoTarget", { tool });
  return { name, transportType: "stdio", command, args, url: "", env: a.env };
}

/** `claude mcp add-json <name> '<json>'`. */
function fromAddJson(words: string[]): ParsedServer | Unreadable {
  const a = readArgs(words, { "-s": "value", "--scope": "value" }, false);
  if ("kind" in a) return a;
  const [name, json] = [...a.positionals, ...a.rest];
  if (name === undefined) return unreadable("errCommandNoName", { tool: "claude mcp add-json" });
  if (json === undefined) return unreadable("errCommandNoTarget", { tool: "claude mcp add-json" });
  try {
    return parseServerConfig(name, JSON.parse(json));
  } catch (error) {
    return jsonSyntaxError(json, error) as Unreadable;
  }
}

/** A plain command: leading `KEY=value` assignments, then program + args. */
function fromPlain(words: string[]): ParsedServer {
  let i = words[0] === "env" ? 1 : 0;
  const env: ParsedEnvVar[] = [];
  for (; i < words.length && ASSIGNMENT_RE.test(words[i]); i++) env.push(pair(words[i], "="));
  const [command, ...args] = words.slice(i);
  return {
    name: nameFromCommand(command, args),
    transportType: "stdio",
    command,
    args,
    url: "",
    env,
  };
}

function result(server: ParsedServer | Unreadable): PasteResult {
  return "kind" in server ? server : { kind: "servers", source: "command", servers: [server] };
}

/** Read `text` as one command line, or `null` when it is not one. */
export function parseCommandPaste(text: string): PasteResult | null {
  const line = text
    .replace(/\\\r?\n/g, " ")
    .replace(/^\s*[$>]\s+/, "")
    .trim();
  if (line.includes("\n")) return null;
  const words = shellSplit(line);
  const first = (words ?? line.split(/\s+/)).find((w) => !ASSIGNMENT_RE.test(w) && w !== "env");
  if (first === undefined || !looksLikeProgram(first)) return null;
  if (looksLikeProse(line, words ?? line.split(/\s+/))) return null;
  if (words === null) return unreadable("errCommandQuote");

  if ((words[0] === "claude" || words[0] === "codex") && words[1] === "mcp") {
    const tool = `${words[0]} mcp ${words[2] ?? ""}`.trim();
    if (words[0] === "claude" && words[2] === "add-json")
      return result(fromAddJson(words.slice(3)));
    if (words[2] !== "add") return unreadable("errCommandNotAdd", { tool });
    const variadic = words[0] === "claude";
    const a = readArgs(words.slice(3), variadic ? CLAUDE_FLAGS : CODEX_FLAGS, variadic);
    return result("kind" in a ? a : fromAdd(tool, a));
  }
  const plain = fromPlain(words);
  return plain.command === undefined ? null : result(plain);
}
