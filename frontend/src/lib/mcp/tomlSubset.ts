// frontend/src/lib/mcp/tomlSubset.ts
//
// A small TOML reader — only the subset MCP server configs use (Codex's
// `[mcp_servers.<name>]` tables), so the paste box needs no dependency:
//
//   - table headers `[a.b]`, `[a."quoted b"]`; dotted keys `a.b = …`
//   - basic strings "…" (escapes \" \\ \n \t \r \b \f \uXXXX \UXXXXXXXX),
//     literal strings '…', integers, floats, booleans
//   - arrays (may span lines, comments inside, trailing comma), inline tables
//   - `#` comments
//
// Anything else (array tables `[[…]]`, multi-line strings, dates) is refused
// with its line number rather than half-read.

type TomlValue = string | number | boolean | TomlValue[] | TomlTable;
export interface TomlTable {
  [key: string]: TomlValue;
}

export type TomlResult =
  | { ok: true; value: TomlTable }
  | { ok: false; line: number; detail: string };

class TomlError extends Error {
  constructor(
    readonly pos: number,
    message: string,
  ) {
    super(message);
  }
}

const BARE_KEY = /[A-Za-z0-9_-]/;
const ESCAPES: Record<string, string> = {
  '"': '"',
  "\\": "\\",
  n: "\n",
  t: "\t",
  r: "\r",
  b: "\b",
  f: "\f",
};

function isTable(v: TomlValue | undefined): v is TomlTable {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

class Reader {
  i = 0;
  constructor(readonly s: string) {}

  fail(message: string): never {
    throw new TomlError(this.i, message);
  }
  peek(n = 0): string {
    return this.s[this.i + n] ?? "";
  }
  /** Spaces and tabs only. */
  skipSpace(): void {
    while (this.peek() === " " || this.peek() === "\t") this.i++;
  }
  skipComment(): void {
    if (this.peek() === "#") while (this.i < this.s.length && this.peek() !== "\n") this.i++;
  }
  /** Whitespace, newlines and comments (inside arrays, between statements). */
  skipBlank(): void {
    for (;;) {
      this.skipSpace();
      this.skipComment();
      if (this.peek() === "\n" || this.peek() === "\r") this.i++;
      else return;
    }
  }
  /** The rest of a line after a statement: only space and a comment. */
  endOfLine(): void {
    this.skipSpace();
    this.skipComment();
    if (this.i < this.s.length && this.peek() !== "\n" && this.peek() !== "\r") {
      this.fail(`unexpected "${this.peek()}" after a value`);
    }
  }

  key(): string {
    const c = this.peek();
    if (c === '"') return this.basicString();
    if (c === "'") return this.literalString();
    const start = this.i;
    while (BARE_KEY.test(this.peek())) this.i++;
    if (start === this.i)
      this.fail(c ? `unexpected "${c}" where a key was expected` : "a key is missing");
    return this.s.slice(start, this.i);
  }
  keyPath(): string[] {
    const path = [this.key()];
    for (;;) {
      this.skipSpace();
      if (this.peek() !== ".") return path;
      this.i++;
      this.skipSpace();
      path.push(this.key());
    }
  }

  basicString(): string {
    if (this.s.startsWith('"""', this.i)) this.fail("multi-line strings are not supported");
    this.i++;
    let out = "";
    for (;;) {
      const c = this.peek();
      if (c === "" || c === "\n") this.fail("a string is not closed");
      this.i++;
      if (c === '"') return out;
      if (c !== "\\") {
        out += c;
        continue;
      }
      const e = this.peek();
      this.i++;
      if (e in ESCAPES) out += ESCAPES[e];
      else if (e === "u" || e === "U") {
        const len = e === "u" ? 4 : 8;
        const hex = this.s.slice(this.i, this.i + len);
        if (!new RegExp(`^[0-9a-fA-F]{${len}}$`).test(hex)) this.fail("a bad \\u escape");
        out += String.fromCodePoint(parseInt(hex, 16));
        this.i += len;
      } else this.fail(`an unknown escape "\\${e}"`);
    }
  }
  literalString(): string {
    if (this.s.startsWith("'''", this.i)) this.fail("multi-line strings are not supported");
    const end = this.s.indexOf("'", this.i + 1);
    const nl = this.s.indexOf("\n", this.i + 1);
    if (end < 0 || (nl >= 0 && nl < end)) this.fail("a string is not closed");
    const out = this.s.slice(this.i + 1, end);
    this.i = end + 1;
    return out;
  }

  value(): TomlValue {
    const c = this.peek();
    if (c === '"') return this.basicString();
    if (c === "'") return this.literalString();
    if (c === "[") return this.array();
    if (c === "{") return this.inlineTable();
    const word = /^(?:true|false|[+-]?\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)(?![\w:-])/.exec(
      this.s.slice(this.i),
    );
    if (!word) this.fail(c ? `unsupported value starting "${c}"` : "a value is missing");
    this.i += word[0].length;
    if (word[0] === "true" || word[0] === "false") return word[0] === "true";
    return Number(word[0].replace(/_/g, ""));
  }
  array(): TomlValue[] {
    this.i++;
    const out: TomlValue[] = [];
    for (;;) {
      this.skipBlank();
      if (this.peek() === "]") {
        this.i++;
        return out;
      }
      out.push(this.value());
      this.skipBlank();
      if (this.peek() === ",") this.i++;
      else if (this.peek() !== "]") this.fail('expected "," or "]" in an array');
    }
  }
  inlineTable(): TomlTable {
    this.i++;
    const out: TomlTable = {};
    this.skipSpace();
    if (this.peek() === "}") {
      this.i++;
      return out;
    }
    for (;;) {
      this.skipSpace();
      this.assign(out);
      this.skipSpace();
      if (this.peek() === "}") {
        this.i++;
        return out;
      }
      if (this.peek() !== ",") this.fail('expected "," or "}" in an inline table');
      this.i++;
    }
  }

  /** `key.path = value` into `table`. */
  assign(table: TomlTable): void {
    const path = this.keyPath();
    this.skipSpace();
    if (this.peek() !== "=") this.fail('expected "=" after a key');
    this.i++;
    this.skipSpace();
    const leaf = path.pop() as string;
    const target = descend(table, path, this);
    if (leaf in target) this.fail(`"${leaf}" is defined twice`);
    target[leaf] = this.value();
  }
}

/** The table at `path` under `root`, creating missing tables on the way. */
function descend(root: TomlTable, path: string[], r: Reader): TomlTable {
  let t = root;
  for (const k of path) {
    const next = t[k];
    if (next === undefined) t[k] = {};
    else if (!isTable(next)) r.fail(`"${k}" is not a table`);
    t = t[k] as TomlTable;
  }
  return t;
}

export function parseToml(text: string): TomlResult {
  const r = new Reader(text);
  const root: TomlTable = {};
  let current = root;
  try {
    for (;;) {
      r.skipBlank();
      if (r.i >= text.length) return { ok: true, value: root };
      if (r.peek() === "[") {
        if (r.peek(1) === "[") r.fail("array tables [[…]] are not supported");
        r.i++;
        r.skipSpace();
        const path = r.keyPath();
        if (r.peek() !== "]") r.fail('expected "]" to close a table header');
        r.i++;
        current = descend(root, path, r);
      } else {
        r.assign(current);
      }
      r.endOfLine();
    }
  } catch (error) {
    if (!(error instanceof TomlError)) throw error;
    const line = text.slice(0, error.pos).split("\n").length;
    return { ok: false, line, detail: error.message };
  }
}
