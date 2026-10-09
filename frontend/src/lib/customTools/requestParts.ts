// src/lib/customTools/requestParts.ts — a tool's request split into the parts the editor shows (the path, its
// query pairs) and where each argument is used. Holes follow the gateway's rules (backend
// domain/mcp/http_api_render.py): `{name}` is an argument, `{env:NAME}` an environment's variable, and an argument
// no hole names is never sent.

/** `{name}` — an argument hole, as the gateway reads it. */
const HOLE = /\{([A-Za-z_][A-Za-z0-9_.-]*)\}/g;

/** One `key=value` pair of the path's query string, as written (holes and all). */
export interface QueryPair {
  key: string;
  value: string;
}

/** Where one argument goes. */
export interface ArgumentUse {
  where: "path" | "query" | "header" | "body";
  /** The query key or header name it fills; empty for the path and the body. */
  key: string;
}

/** The argument holes a template names, in order, each once. */
export function holesIn(text: string): string[] {
  const seen: string[] = [];
  for (const m of text.matchAll(HOLE)) if (!seen.includes(m[1])) seen.push(m[1]);
  return seen;
}

/** The path before `?`, and its query pairs. */
export function splitPath(path: string): { base: string; query: QueryPair[] } {
  const at = path.indexOf("?");
  if (at < 0) return { base: path, query: [] };
  const query = path
    .slice(at + 1)
    .split("&")
    .filter((part) => part !== "")
    .map((part) => {
      const eq = part.indexOf("=");
      return eq < 0
        ? { key: part, value: "" }
        : { key: part.slice(0, eq), value: part.slice(eq + 1) };
    });
  return { base: path.slice(0, at), query };
}

/** The path the base and pairs make; a pair with neither key nor value is left out, while one being typed stays. */
export function joinPath(base: string, query: readonly QueryPair[]): string {
  const pairs = query
    .filter((p) => p.key !== "" || p.value !== "")
    .map((p) => `${p.key}=${p.value}`);
  return pairs.length > 0 ? `${base}?${pairs.join("&")}` : base;
}

interface RequestTemplate {
  path: string;
  headers: readonly { key: string; value: string }[];
  body: string;
  /** A GET sends no body, so a body's holes use nothing. */
  sendsBody: boolean;
}

/** Each argument hole of the request and where it sits. */
export function argumentUses(request: RequestTemplate): Map<string, ArgumentUse[]> {
  const uses = new Map<string, ArgumentUse[]>();
  const add = (name: string, use: ArgumentUse) => uses.set(name, [...(uses.get(name) ?? []), use]);
  const { base, query } = splitPath(request.path);
  for (const name of holesIn(base)) add(name, { where: "path", key: "" });
  for (const pair of query)
    for (const name of holesIn(pair.value)) add(name, { where: "query", key: pair.key });
  for (const h of request.headers) {
    if (!h.key.trim()) continue;
    for (const name of holesIn(h.value)) add(name, { where: "header", key: h.key.trim() });
  }
  if (request.sendsBody)
    for (const name of holesIn(request.body)) add(name, { where: "body", key: "" });
  return uses;
}

/** The arguments no hole names, and the holes no argument names. */
export function argumentProblems(
  argNames: readonly string[],
  uses: Map<string, ArgumentUse[]>,
): { unused: string[]; missing: string[] } {
  const named = argNames.filter(Boolean);
  return {
    unused: named.filter((name) => !uses.has(name)),
    missing: [...uses.keys()].filter((name) => !named.includes(name)),
  };
}
