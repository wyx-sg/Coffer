// src/lib/customTools/sentRequest.ts — the request one test run sends, as the Test tab shows it before the run: the
// environment's preview (environmentContext.requestPreview) with the sample values put in by the gateway's rules
// (backend domain/mcp/http_api_render.py render_request). A path hole with no value stays `{name}` (the run is
// refused for it); a query pair or tool header whose input has no value is left out; a list fills one query pair
// per item; the body is the template filled (bodyTemplate.fillBodyTemplate), or — for a POST, PUT or PATCH with
// no template — the inputs the request uses nowhere else, as JSON. A body adds `Content-Type: application/json`
// unless a header already sets it.
import { fillBodyTemplate } from "./bodyTemplate";
import type { PreviewHeaderLine, RequestPreviewLines } from "./environmentContext";
import { argumentUses } from "./requestParts";

const HOLE = /\{([A-Za-z_][A-Za-z0-9_.-]*)\}/g;
const WHOLE_HOLE = /^\{([A-Za-z_][A-Za-z0-9_.-]*)\}$/;
const BODY_METHODS = new Set(["POST", "PUT", "PATCH"]);

function scalar(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function present(values: Record<string, unknown>, name: string): boolean {
  return values[name] !== undefined && values[name] !== null;
}

/** `text` with every hole filled; null when one has no value. */
function fillText(
  text: string,
  values: Record<string, unknown>,
  encode: (v: string) => string,
): string | null {
  let missing = false;
  const out = text.replace(HOLE, (_, name: string) => {
    if (!present(values, name)) {
      missing = true;
      return "";
    }
    return encode(scalar(values[name]));
  });
  return missing ? null : out;
}

export interface SentRequest {
  url: string;
  headers: PreviewHeaderLine[];
  body: string | null;
  /** Path inputs without a value: the run is refused until they have one. */
  missingPath: string[];
}

export function sentRequest(
  preview: RequestPreviewLines,
  tool: {
    method: string;
    path: string;
    headers?: Record<string, string> | null;
    body_template?: string | null;
  },
  values: Record<string, unknown>,
  variables: Record<string, string>,
): SentRequest {
  const at = preview.url.indexOf("?");
  const base = at < 0 ? preview.url : preview.url.slice(0, at);
  const query = at < 0 ? "" : preview.url.slice(at + 1);
  const missingPath: string[] = [];
  const path = base.replace(HOLE, (hole, name: string) => {
    if (!present(values, name)) {
      missingPath.push(name);
      return hole;
    }
    return encodeURIComponent(scalar(values[name]));
  });
  const pairs: string[] = [];
  for (const raw of query.split("&")) {
    if (!raw) continue;
    const eq = raw.indexOf("=");
    const key = eq < 0 ? raw : raw.slice(0, eq);
    const value = eq < 0 ? "" : raw.slice(eq + 1);
    const whole = WHOLE_HOLE.exec(value);
    if (whole) {
      if (!present(values, whole[1])) continue;
      const v = values[whole[1]];
      for (const item of Array.isArray(v) ? v : [v])
        pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(scalar(item))}`);
      continue;
    }
    const filled = fillText(value, values, (v) => v);
    if (filled !== null) pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(filled)}`);
  }
  const url = path + (pairs.length > 0 ? `?${pairs.join("&")}` : "");

  const headers: PreviewHeaderLine[] = [];
  for (const line of preview.headers) {
    if (line.from !== "tool" || line.value === null) {
      headers.push(line);
      continue;
    }
    const value = fillText(line.value, values, (v) => v);
    if (value !== null) headers.push({ ...line, value });
  }

  let body: string | null = null;
  if (tool.body_template) {
    body = fillBodyTemplate(tool.body_template, values, variables);
  } else if (BODY_METHODS.has(tool.method)) {
    const used = argumentUses({
      path: tool.path,
      headers: Object.entries(tool.headers ?? {}).map(([key, value]) => ({ key, value })),
      body: "",
      sendsBody: false,
    });
    const rest = Object.fromEntries(Object.entries(values).filter(([name]) => !used.has(name)));
    if (Object.keys(rest).length > 0) body = JSON.stringify(rest, null, 2);
  }
  if (body !== null && !headers.some((h) => h.name.toLowerCase() === "content-type"))
    headers.push({ name: "Content-Type", value: "application/json", secret: null, from: "tool" });
  return { url, headers, body, missingPath };
}
