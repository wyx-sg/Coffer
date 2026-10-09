import { describe, expect, test } from "vitest";

import {
  describeRule,
  diagnosticHeadersProblem,
  emptyRule,
  headerProblem,
  messageProblem,
  ruleProblem,
  rulesValid,
  splitList,
} from "./responseRules";

describe("responseRules", () => {
  test("splitList trims and drops empty entries", () => {
    expect(splitList(" OK, 0 ,, ")).toEqual(["OK", "0"]);
    expect(splitList("")).toEqual([]);
  });

  test("a header rule needs a legal, non-credential name and a success value", () => {
    const rule = { ...emptyRule(), name: "X-Result-Code", ok_values: ["OK"] };
    expect(ruleProblem(rule)).toBeNull();
    expect(ruleProblem({ ...rule, name: "" })).toBe("name");
    expect(ruleProblem({ ...rule, name: "Set-Cookie" })).toBe("refused");
    expect(ruleProblem({ ...rule, name: "bad name" })).toBe("invalid");
    expect(ruleProblem({ ...rule, ok_values: [] })).toBe("noValues");
  });

  test("a JSON rule's name is a pointer", () => {
    const rule = { source: "json" as const, name: "status/code", ok_values: ["0"] };
    expect(ruleProblem(rule)).toBe("pointer");
    expect(ruleProblem({ ...rule, name: "/status/code" })).toBeNull();
  });

  test("a status rule takes statuses 100 to 599", () => {
    const rule = { source: "status" as const, ok_values: ["200", "204"] };
    expect(ruleProblem(rule)).toBeNull();
    expect(ruleProblem({ ...rule, ok_values: ["99"] })).toBe("status");
    expect(ruleProblem({ ...rule, ok_values: ["600"] })).toBe("status");
    expect(ruleProblem({ ...rule, ok_values: ["ok"] })).toBe("status");
  });

  test("the message field is checked like a name", () => {
    const base = { source: "status" as const, ok_values: ["200"] };
    expect(messageProblem({ ...base, message: { source: "json", name: "msg" } })).toBe("pointer");
    expect(messageProblem({ ...base, message: { source: "header", name: "X-Text" } })).toBeNull();
    expect(messageProblem(base)).toBeNull();
  });

  test("rulesValid caps the count", () => {
    const ok = { source: "status" as const, ok_values: ["200"] };
    expect(rulesValid([ok])).toBe(true);
    expect(rulesValid(Array.from({ length: 11 }, () => ok))).toBe(false);
  });

  test("diagnostic headers refuse credentials", () => {
    expect(diagnosticHeadersProblem(["X-Request-Id"])).toBeNull();
    expect(diagnosticHeadersProblem(["Cookie"])).toBe("refused");
    expect(headerProblem("API-Key")).toBe("refused");
  });

  test("describeRule reads on one line", () => {
    expect(
      describeRule({
        source: "header",
        name: "x-result-code",
        ok_values: ["OK"],
        missing: "ok",
        message: { source: "header", name: "x-result-text" },
      }),
    ).toBe("header x-result-code ∈ OK · missing: success · message: header x-result-text");
    expect(
      describeRule({ source: "json", name: "/code", ok_values: ["0", "1"], missing: "error" }),
    ).toBe("json /code ∈ 0, 1 · missing: failure");
    expect(describeRule({ source: "status", ok_values: ["200"] })).toBe("status ∈ 200");
  });
});
