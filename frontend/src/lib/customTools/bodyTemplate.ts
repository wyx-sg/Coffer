// src/lib/customTools/bodyTemplate.ts — a tool's JSON body template as the editor shows it: laid out with indents,
// checked, and filled with sample values for the Test tab's preview. Holes follow the gateway's rules (backend
// domain/mcp/http_api_render.py): outside a JSON string `{name}` becomes the argument's JSON value and `{env:NAME}`
// the variable's text; inside a string both become text. A hole outside a string is not JSON by itself, so the
// template is never parsed as it is: each hole is read as one token and kept exactly as written.

/** `{name}` or `{env:NAME}` at the start of the text. */
const HOLE_AT = /^\{(env:[A-Za-z_][A-Za-z0-9_]{0,63}|[A-Za-z_][A-Za-z0-9_.-]*)\}/;

interface Piece {
  kind: "string" | "hole" | "char";
  text: string;
}

/** The template cut into strings (quotes included), holes outside strings, and single characters. */
function pieces(template: string): Piece[] {
  const out: Piece[] = [];
  let i = 0;
  while (i < template.length) {
    const ch = template[i];
    if (ch === '"') {
      let j = i + 1;
      while (j < template.length && template[j] !== '"') j += template[j] === "\\" ? 2 : 1;
      out.push({ kind: "string", text: template.slice(i, j + 1) });
      i = j + 1;
      continue;
    }
    if (ch === "{") {
      const m = HOLE_AT.exec(template.slice(i));
      if (m) {
        out.push({ kind: "hole", text: m[0] });
        i += m[0].length;
        continue;
      }
    }
    out.push({ kind: "char", text: ch });
    i += 1;
  }
  return out;
}

/** Where the template stops being JSON, once every hole outside a string reads as a value; null when it is JSON. */
export function bodyTemplateProblem(template: string): { line: number; column: number } | null {
  if (template.trim() === "") return null;
  // A hole becomes `0` padded to its own length, so a position in the error is a position in the template.
  const masked = pieces(template)
    .map((p) => (p.kind === "hole" ? "0".padEnd(p.text.length, " ") : p.text))
    .join("");
  try {
    JSON.parse(masked);
    return null;
  } catch (e) {
    const message = e instanceof Error ? e.message : "";
    const lineCol = /line (\d+) column (\d+)/.exec(message);
    if (lineCol) return { line: Number(lineCol[1]), column: Number(lineCol[2]) };
    const at = /position (\d+)/.exec(message);
    const pos = at ? Number(at[1]) : masked.length;
    const before = template.slice(0, pos).split("\n");
    return { line: before.length, column: before[before.length - 1].length + 1 };
  }
}

/** The template laid out two spaces per level; null when it is not JSON (it is then left as written). Numbers, key
 *  order and every string are kept exactly: only whitespace between tokens changes. */
export function formatBodyTemplate(template: string): string | null {
  if (template.trim() === "" || bodyTemplateProblem(template) !== null) return null;
  const parts = pieces(template).filter((p) => p.kind !== "char" || p.text.trim() !== "");
  let out = "";
  let depth = 0;
  const newline = () => "\n" + "  ".repeat(depth);
  parts.forEach((p, i) => {
    if (p.kind !== "char") {
      out += p.text;
      return;
    }
    const next = parts[i + 1]?.text;
    if (p.text === "{" || p.text === "[") {
      const close = p.text === "{" ? "}" : "]";
      if (next === close) {
        out += p.text;
        return;
      }
      depth += 1;
      out += p.text + newline();
    } else if (p.text === "}" || p.text === "]") {
      const prev = parts[i - 1]?.text;
      if (prev === (p.text === "}" ? "{" : "[")) {
        out += p.text;
        return;
      }
      depth -= 1;
      out += newline() + p.text;
    } else if (p.text === ",") {
      out += "," + newline();
    } else if (p.text === ":") {
      out += ": ";
    } else {
      out += p.text;
    }
  });
  return out;
}

/** A template a tool was saved with on one line reads better laid out; any other is shown as written. */
export function bodyTemplateShown(template: string): string {
  if (template.includes("\n")) return template;
  return formatBodyTemplate(template) ?? template;
}

/** JSON-escape `text` for the inside of a string (without the quotes). */
function escaped(text: string): string {
  return JSON.stringify(text).slice(1, -1);
}

function scalar(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** The body a run sends, filled the gateway's way: an input outside a string becomes its JSON value (`null` when it
 *  has none), inside a string its text (nothing when it has none); a variable becomes its text, and one the
 *  environment does not define stays as written. Laid out when the result is JSON. */
export function fillBodyTemplate(
  template: string,
  values: Record<string, unknown>,
  variables: Record<string, string>,
): string {
  const fillIn = (hole: string, inString: boolean): string => {
    const name = hole.slice(1, -1);
    if (name.startsWith("env:")) {
      const v = variables[name.slice(4)];
      return v === undefined ? hole : inString ? escaped(v) : v;
    }
    const v = values[name];
    if (inString) return v === undefined || v === null ? "" : escaped(scalar(v));
    return JSON.stringify(v ?? null);
  };
  const filled = pieces(template)
    .map((p) =>
      p.kind === "hole"
        ? fillIn(p.text, false)
        : p.kind === "string"
          ? p.text.replace(new RegExp(HOLE_AT.source.slice(1), "g"), (m) => fillIn(m, true))
          : p.text,
    )
    .join("");
  return formatBodyTemplate(filled) ?? filled;
}
