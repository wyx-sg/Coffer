// src/lib/customTools/schemaArgs.test.ts — argument rows round-trip a tool's input schema without losing what they do not edit.
import { describe, expect, test } from "vitest";

import { argsFromSchema, schemaFromArgs, testArguments } from "./schemaArgs";

const schema = {
  type: "object",
  additionalProperties: false,
  properties: {
    id: { type: "string", description: "Invoice id", format: "uuid" },
    status: { type: "string", enum: ["open", "paid"] },
    filter: {
      type: "object",
      properties: { from: { type: "string" }, to: { type: "string" } },
      required: ["from"],
    },
    limit: { type: "integer" },
  },
  required: ["id"],
};

describe("schemaArgs", () => {
  test("reads each top-level property as a row, with enum and nested types told apart", () => {
    const rows = argsFromSchema(schema);
    expect(rows.map((r) => [r.name, r.type, r.required])).toEqual([
      ["id", "string", true],
      ["status", "enum", false],
      ["filter", "other", false],
      ["limit", "integer", false],
    ]);
    expect(rows[1].enumValues).toBe("open, paid");
    expect(rows[2].rawType).toBe("object");
  });

  test("writes back the edits and keeps a nested argument's schema and other keys untouched", () => {
    const rows = argsFromSchema(schema);
    rows[0] = { ...rows[0], description: "The invoice" };
    rows[2] = { ...rows[2], description: "Date range", required: true };
    rows[3] = { ...rows[3], type: "number" };
    const next = schemaFromArgs(rows, schema);
    expect(next.additionalProperties).toBe(false);
    expect(next.required).toEqual(["id", "filter"]);
    const props = next.properties as Record<string, Record<string, unknown>>;
    expect(props.id).toEqual({ type: "string", description: "The invoice", format: "uuid" });
    expect(props.filter).toEqual({ ...schema.properties.filter, description: "Date range" });
    expect(props.limit).toEqual({ type: "number" });
    expect(props.status).toEqual({ type: "string", enum: ["open", "paid"] });
  });

  test("drops unnamed rows and the required list when nothing is required", () => {
    const limit = argsFromSchema(schema)[3];
    const next = schemaFromArgs([limit, { ...limit, name: "" }], {
      type: "object",
      properties: {},
      required: ["gone"],
    });
    expect(Object.keys(next.properties as object)).toEqual(["limit"]);
    expect(next.required).toBeUndefined();
  });

  test("types test values by their row and leaves empty ones out", () => {
    const rows = argsFromSchema(schema);
    expect(
      testArguments(rows, { id: "7", limit: "20", filter: '{"from":"a"}', status: "" }),
    ).toEqual({ id: "7", limit: 20, filter: { from: "a" } });
  });
});
