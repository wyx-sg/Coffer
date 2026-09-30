import { describe, expect, test } from "vitest";
import { parseToml } from "./tomlSubset";

describe("parseToml", () => {
  test("reads tables, dotted and quoted keys, and every supported value", () => {
    const r = parseToml(
      [
        "# a comment",
        "top = 1",
        "[mcp_servers.docs]  # trailing comment",
        'command = "npx"',
        "args = [",
        '  "-y", # inside an array',
        "  'literal\\path',",
        "]",
        "enabled = true",
        "startup_timeout_sec = 10.5",
        'env = { A = "1", "B C" = "x\\ty\\u00e9" }',
        '[mcp_servers."my server".env]',
        'K = "v"',
        "sub.key = -3",
      ].join("\n"),
    );
    expect(r).toEqual({
      ok: true,
      value: {
        top: 1,
        mcp_servers: {
          docs: {
            command: "npx",
            args: ["-y", "literal\\path"],
            enabled: true,
            startup_timeout_sec: 10.5,
            env: { A: "1", "B C": "x\tyé" },
          },
          "my server": { env: { K: "v", sub: { key: -3 } } },
        },
      },
    });
  });

  test("an empty document and an empty array / inline table", () => {
    expect(parseToml("")).toEqual({ ok: true, value: {} });
    expect(parseToml("a = []\nb = {}")).toEqual({ ok: true, value: { a: [], b: {} } });
  });

  test.each([
    ['a = "open', 1, "a string is not closed"],
    ["\n\n[[mcp_servers]]", 3, "array tables [[…]] are not supported"],
    ['x = 1\ny = """multi"""', 2, "multi-line strings are not supported"],
    ["a = 1\na = 2", 2, '"a" is defined twice'],
    ["a = 1979-05-27", 1, 'unsupported value starting "1"'],
    ["a = nope", 1, 'unsupported value starting "n"'],
    ["a 1", 1, 'expected "=" after a key'],
    ["[a\nb = 1", 1, 'expected "]" to close a table header'],
    ['a = "x" b', 1, 'unexpected "b" after a value'],
    ["a = [1 2]", 1, 'expected "," or "]" in an array'],
    ['a = "\\q"', 1, 'an unknown escape "\\q"'],
    ["a = 1\n[a]", 2, '"a" is not a table'],
  ])("refuses %j at line %i", (text, line, detail) => {
    expect(parseToml(text)).toEqual({ ok: false, line, detail });
  });
});
