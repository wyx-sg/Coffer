// src/lib/customTools/environmentContext.ts — the one environment a tool form previews and tests in
// (spec mcp-gateway "Choose a custom tool's environment on every call"): which environment is
// chosen and whether it can run, its secret, its effective timeout, and the request the form
// would send there. The request follows the daemon's rules (domain/mcp/http_api_request.py
// build_request, http_api_render.py render_request): the base URL without its trailing "/", then
// the path with `{env:NAME}` filled from the environment; the environment's plain headers, a tool
// header replacing one of the same name, `{env:NAME}` filled in it; the environment's secret
// headers last, replacing any spelling of their name. `{argument}` holes stay as they are — the
// arguments arrive only when the request runs, and the query is shown before it is percent-encoded.
import type {
  CustomToolEnvironment,
  CustomToolGroup,
  CustomToolHeaderOut,
} from "@/lib/api/customTools";

/** The environment a form names: usable, or why not. */
export type EnvironmentChoice =
  | { state: "ok"; environment: CustomToolEnvironment }
  | { state: "disabled"; name: string; environment: CustomToolEnvironment }
  | { state: "deleted"; name: string }
  | { state: "none" };

type WithEnvironments = Pick<CustomToolGroup, "environments">;

export function enabledEnvironments(group: WithEnvironments): CustomToolEnvironment[] {
  return (group.environments ?? []).filter((e) => e.enabled);
}

/** Where a form starts: the first environment that is on ("" when none is). */
export function firstEnabled(group: WithEnvironments): string {
  return enabledEnvironments(group)[0]?.name ?? "";
}

/** The environment `name` as it is now — never another one in its place. */
export function chooseEnvironment(group: WithEnvironments, name: string): EnvironmentChoice {
  if (name === "") return { state: "none" };
  const environment = (group.environments ?? []).find((e) => e.name === name);
  if (!environment) return { state: "deleted", name };
  if (!environment.enabled) return { state: "disabled", name, environment };
  return { state: "ok", environment };
}

/** The timeout a request in `env` waits, and whose it is. */
export function effectiveTimeout(
  group: Pick<CustomToolGroup, "timeout_seconds">,
  env: Pick<CustomToolEnvironment, "timeout_seconds">,
): { seconds: number; source: "environment" | "group" } {
  return env.timeout_seconds != null
    ? { seconds: env.timeout_seconds, source: "environment" }
    : { seconds: group.timeout_seconds, source: "group" };
}

/** The first secret this environment's headers read, or null — never another environment's. */
export function environmentSecret(env: Pick<CustomToolEnvironment, "headers">): string | null {
  return env.headers.find((h) => h.secret)?.secret ?? null;
}

const ENV_HOLE = /\{env:([A-Za-z_][A-Za-z0-9_]{0,63})\}/g;

/** `text` with `{env:NAME}` filled; an undefined name stays, and is reported. */
function fillEnv(
  text: string,
  variables: Record<string, string>,
  missing: Set<string>,
  encode: (v: string) => string,
): string {
  return text.replace(ENV_HOLE, (hole, name: string) => {
    if (name in variables) return encode(variables[name]);
    missing.add(name);
    return hole;
  });
}

interface PreviewHeaderLine {
  name: string;
  /** A plain value, or null for a secret header. */
  value: string | null;
  /** Set for a secret header: the environment's own row (secret, scheme, state). */
  secret: CustomToolHeaderOut | null;
  /** Where the value comes from. */
  from: "environment" | "tool";
}

export interface RequestPreviewLines {
  url: string;
  headers: PreviewHeaderLine[];
  /** `{env:NAME}` the tool uses that this environment does not define. */
  missingVariables: string[];
}

/** The request a draft `{ path, headers }` would send in `env`. */
export function requestPreview(
  env: Pick<CustomToolEnvironment, "base_url" | "headers" | "variables">,
  tool: { path: string; headers?: Record<string, string> | null },
): RequestPreviewLines {
  const variables = env.variables ?? {};
  const missing = new Set<string>();
  const [pathPart, query] = splitOnce(tool.path, "?");
  const path = fillEnv(pathPart, variables, missing, (v) =>
    encodeURIComponent(v).replace(/%2F/gi, "/"),
  );
  const filledQuery = query === null ? "" : "?" + fillEnv(query, variables, missing, (v) => v);
  const url = env.base_url.replace(/\/+$/, "") + path + filledQuery;

  const lines = new Map<string, PreviewHeaderLine>();
  for (const h of env.headers)
    if (!h.secret)
      lines.set(h.name, { name: h.name, value: h.value ?? "", secret: null, from: "environment" });
  for (const [name, template] of Object.entries(tool.headers ?? {}))
    if (name.trim() !== "")
      lines.set(name, {
        name,
        value: fillEnv(template, variables, missing, (v) => v),
        secret: null,
        from: "tool",
      });
  for (const h of env.headers) {
    if (!h.secret) continue;
    for (const key of [...lines.keys()])
      if (key.toLowerCase() === h.name.toLowerCase()) lines.delete(key);
    lines.set(h.name, { name: h.name, value: null, secret: h, from: "environment" });
  }
  return { url, headers: [...lines.values()], missingVariables: [...missing] };
}

function splitOnce(text: string, sep: string): [string, string | null] {
  const i = text.indexOf(sep);
  return i < 0 ? [text, null] : [text.slice(0, i), text.slice(i + 1)];
}
