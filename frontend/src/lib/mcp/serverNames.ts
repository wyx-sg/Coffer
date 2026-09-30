// frontend/src/lib/mcp/serverNames.ts
//
// MCP server names: the rule the daemon registers a name under, how a pasted
// key / package / host becomes such a name, and de-duplication within one
// paste. Pure.

import type { ParsedServer } from "./pasteTypes";

/**
 * The longest name the daemon registers a new MCP server under (spec
 * mcp-gateway "Manage MCP servers as resources"). The name is fixed after
 * registration and prefixes every tool name a client sees
 * (`mcp__coffer__<server>__<tool>`), so the review flags a longer one before
 * submit rather than letting the registration be refused.
 */
export const MCP_SERVER_NAME_MAX = 24;

/**
 * The backend's name rule: one safe label (`domain/resource.py`
 * `_NAME_PATTERN`), with `__` reserved as the tool namespace separator
 * (`application/mcp/kind.py` `_validate_mcp_name`).
 */
const NAME_PATTERN = /^[a-zA-Z0-9_.-]+$/;

/** What normalising keeps: the backend's characters, in lower case. */
const NAME_OUTSIDE = /[^a-z0-9_.-]+/g;

/** The fallback when nothing of a pasted name survives normalising. */
const FALLBACK_NAME = "server";

/** Whether `name` is over the registration cap. */
export function serverNameTooLong(name: string): boolean {
  return name.length > MCP_SERVER_NAME_MAX;
}

/** Whether the daemon would register a new server under `name`. */
export function isValidServerName(name: string): boolean {
  return NAME_PATTERN.test(name) && !name.includes("__") && !serverNameTooLong(name);
}

/**
 * `raw` in the form the daemon registers: lower case, every run of other
 * characters turned into one `-`, `__` runs collapsed to `_` (the separator is
 * reserved), repeated hyphens collapsed, and leading/trailing `-` trimmed.
 * The length is not cut: an over-long name is flagged for the user to shorten.
 */
export function normaliseServerName(raw: string): string {
  const name = raw
    .toLowerCase()
    .replace(NAME_OUTSIDE, "-")
    .replace(/_{2,}/g, "_")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");
  return name === "" ? FALLBACK_NAME : name;
}

const AFFIX_PREFIX = /^(?:mcp[-_]server[-_]|server[-_]|mcp[-_])/;
const AFFIX_SUFFIX = /(?:[-_]mcp[-_]server|[-_]mcp)$/;

/** Drop one `mcp-server-` / `server-` / `mcp-` prefix and one `-mcp-server` /
 *  `-mcp` suffix, unless nothing would be left. */
function stripAffixes(name: string): string {
  const noPrefix = name.replace(AFFIX_PREFIX, "");
  const base = noPrefix === "" ? name : noPrefix;
  const noSuffix = base.replace(AFFIX_SUFFIX, "");
  return noSuffix === "" ? base : noSuffix;
}

/**
 * The name a package suggests: `@scope/` and a trailing `@version` dropped,
 * then the MCP affixes. `@modelcontextprotocol/server-github` -> `github`,
 * `@notionhq/notion-mcp-server` -> `notion`, `mcp-atlassian` -> `atlassian`.
 */
export function nameFromPackage(pkg: string): string {
  let name = pkg.replace(/^@[^/]+\//, "");
  name = name.replace(/@[^@/]*$/, "");
  name = name.replace(/(?:==|>=|<=|~=).*$/, ""); // a pinned Python requirement
  return stripAffixes(name);
}

/** The last path segment of a docker image, without tag or digest. */
function nameFromImage(image: string): string {
  const noDigest = image.split("@")[0];
  const last = noDigest.split("/").pop() ?? noDigest;
  return stripAffixes(last.split(":")[0]);
}

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

const GENERIC_FILES = ["index", "server", "main", "cli", "app"];
const GENERIC_DIRS = ["dist", "build", "src", "lib", "bin", "."];

/** A script path's name: its file name without extension, or its folder's
 *  name when the file name says nothing (`index.js`, `server.py`). */
function nameFromScript(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  const file = (parts.pop() ?? path).replace(/\.[^.]+$/, "");
  const dir = parts.filter((p) => !GENERIC_DIRS.includes(p)).pop();
  return GENERIC_FILES.includes(file) && dir ? stripAffixes(dir) : stripAffixes(file);
}

/** Flags of each launcher that take a value, so the value is not mistaken
 *  for the package / image. */
const VALUE_FLAGS: Record<string, string[]> = {
  npx: ["-p", "--package", "--registry"],
  bunx: ["-p", "--package"],
  uvx: ["--from", "--with", "--python", "-p", "--index", "--index-url"],
  uv: ["--with", "--python", "-p", "--directory", "--project", "--env-file", "--from"],
  docker: [
    ...["-e", "--env", "--env-file", "-v", "--volume", "-p", "--publish", "--name"],
    ...["--network", "-w", "--workdir", "--entrypoint", "-u", "--user", "--mount"],
    ...["-l", "--label", "--platform"],
  ],
};

/** The first argument that is not a flag (nor a flag's value). */
function firstOperand(args: string[], valueFlags: string[] = []): string | undefined {
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a.startsWith("-")) {
      if (!a.includes("=") && valueFlags.includes(a)) i++;
      continue;
    }
    return a;
  }
  return undefined;
}

/**
 * The name a stdio command suggests, before normalising: the package for
 * npx / bunx / pnpm dlx / uvx / `uv run` / `python -m`, the image for
 * `docker run`, the script for node / python / deno / bun, otherwise the
 * program's basename.
 */
export function nameFromCommand(command: string, args: string[]): string {
  const program = basename(command).replace(/\.(?:exe|cmd)$/i, "");
  const pick = (candidate: string | undefined, fn: (s: string) => string) =>
    candidate ? fn(candidate) : program;
  switch (program) {
    case "npx":
    case "bunx":
    case "uvx":
      return pick(firstOperand(args, VALUE_FLAGS[program]), nameFromPackage);
    case "pnpm":
    case "yarn":
    case "bun":
      if (args[0] === "dlx" || args[0] === "x") {
        return pick(firstOperand(args.slice(1)), nameFromPackage);
      }
      return program === "bun" ? pick(firstOperand(args), nameFromScript) : program;
    case "uv": {
      const run = args.indexOf("run");
      if (run < 0) return program;
      return pick(firstOperand(args.slice(run + 1), VALUE_FLAGS.uv), nameFromScript);
    }
    case "docker":
    case "podman":
      if (args[0] !== "run") return program;
      return pick(firstOperand(args.slice(1), VALUE_FLAGS.docker), nameFromImage);
    case "node":
    case "deno":
    case "python":
    case "python3": {
      const m = args.indexOf("-m");
      if (m >= 0 && args[m + 1]) return nameFromPackage(args[m + 1].replace(/_/g, "-"));
      return pick(firstOperand(args.filter((a) => a !== "run")), nameFromScript);
    }
    default:
      return stripAffixes(program);
  }
}

/** Public-suffix second levels common enough to skip (`example.co.uk`). */
const SECOND_LEVEL = new Set(["co", "com", "org", "net", "ac", "gov", "edu"]);
const GENERIC_LABELS = new Set(["www", "mcp", "api"]);

/**
 * The name a URL suggests: its host without leading `www.` / `mcp.` / `api.`
 * labels and the TLD, the most specific remaining label.
 * `https://mcp.example.com/mcp` -> `example`, `http://localhost:3000` -> `localhost`.
 */
export function nameFromUrl(url: string): string {
  let host: string;
  try {
    host = new URL(url).hostname;
  } catch {
    return FALLBACK_NAME;
  }
  if (/^[\d.]+$/.test(host) || host.startsWith("[")) return host;
  const labels = host.split(".").filter(Boolean);
  if (labels.length > 1) labels.pop();
  if (labels.length > 1 && SECOND_LEVEL.has(labels[labels.length - 1])) labels.pop();
  while (labels.length > 1 && GENERIC_LABELS.has(labels[0])) labels.shift();
  return labels[0] ?? FALLBACK_NAME;
}

/**
 * Every server's name normalised (with `originalName` recording a change) and
 * made unique within the paste by suffixing `-2`, `-3`, ….
 */
export function finaliseNames(servers: ParsedServer[]): ParsedServer[] {
  const taken = new Set<string>();
  return servers.map(({ originalName, ...server }) => {
    const spelled = originalName ?? server.name;
    const base = normaliseServerName(server.name);
    let name = base;
    for (let n = 2; taken.has(name); n++) name = `${base}-${n}`;
    taken.add(name);
    return spelled === name ? { ...server, name } : { ...server, name, originalName: spelled };
  });
}
