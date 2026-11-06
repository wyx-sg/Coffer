// src/lib/customTools/schemaArgs.ts — a tool's `input_schema` as editable argument rows, and back.
//
// Only the top-level `properties` are edited. An argument whose schema is an
// object or an array (or anything else the row cannot express) keeps its
// schema untouched: the row shows its type read-only and edits only its
// description and required flag. Every other key of the schema survives too.

/** The types a row can edit; `other` is a schema the row leaves as it is. */
export type ArgType = "string" | "number" | "integer" | "boolean" | "enum" | "other";

/** One editable argument of a draft tool. */
export interface ArgRow {
  name: string;
  type: ArgType;
  /** The schema's own type word for an `other` row (object, array, …). */
  rawType: string;
  required: boolean;
  description: string;
  /** Comma-separated values of an `enum` row. */
  enumValues: string;
  /** The property's original schema, the base every edit is applied over. */
  raw: Record<string, unknown>;
}

type Schema = Record<string, unknown>;

const SIMPLE: readonly string[] = ["string", "number", "integer", "boolean"];

function asObject(value: unknown): Schema {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Schema)
    : {};
}

function rowType(prop: Schema): { type: ArgType; rawType: string } {
  const type = typeof prop.type === "string" ? prop.type : "";
  if (Array.isArray(prop.enum)) return { type: "enum", rawType: type || "string" };
  if (SIMPLE.includes(type)) return { type: type as ArgType, rawType: type };
  return { type: "other", rawType: type || "any" };
}

export function argsFromSchema(schema: Schema): ArgRow[] {
  const props = asObject(schema.properties);
  const required = new Set(Array.isArray(schema.required) ? (schema.required as string[]) : []);
  return Object.entries(props).map(([name, value]) => {
    const raw = asObject(value);
    const { type, rawType } = rowType(raw);
    return {
      name,
      type,
      rawType,
      required: required.has(name),
      description: typeof raw.description === "string" ? raw.description : "",
      enumValues: Array.isArray(raw.enum) ? raw.enum.map(String).join(", ") : "",
      raw,
    };
  });
}

export function emptyArg(): ArgRow {
  return {
    name: "",
    type: "string",
    rawType: "string",
    required: false,
    description: "",
    enumValues: "",
    raw: {},
  };
}

function propertyOf(row: ArgRow): Schema {
  const prop: Schema = { ...row.raw };
  if (row.type !== "other") {
    delete prop.enum;
    if (row.type === "enum") {
      prop.type = "string";
      prop.enum = row.enumValues
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    } else {
      prop.type = row.type;
    }
  }
  if (row.description.trim()) prop.description = row.description.trim();
  else delete prop.description;
  return prop;
}

/** The schema the rows describe, over the original so no other key is lost. */
export function schemaFromArgs(rows: readonly ArgRow[], original: Schema): Schema {
  const named = rows.filter((row) => row.name.trim());
  const properties = Object.fromEntries(named.map((row) => [row.name.trim(), propertyOf(row)]));
  const required = named.filter((row) => row.required).map((row) => row.name.trim());
  const next: Schema = { ...original, type: "object", properties };
  if (required.length > 0) next.required = required;
  else delete next.required;
  return next;
}

/** Typed arguments for a test run from the text the user typed per row; empty
 *  values are left out. A value that does not parse is sent as typed. */
export function testArguments(
  rows: readonly ArgRow[],
  values: Record<string, string>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const row of rows) {
    const text = values[row.name]?.trim() ?? "";
    if (!row.name || text === "") continue;
    out[row.name] = coerce(row, text);
  }
  return out;
}

function coerce(row: ArgRow, text: string): unknown {
  if (row.type === "number" || row.type === "integer") {
    const n = Number(text);
    return Number.isNaN(n) ? text : n;
  }
  if (row.type === "boolean") return text === "true" ? true : text === "false" ? false : text;
  if (row.type === "other") {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }
  return text;
}
