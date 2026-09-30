import { describe, expect, test } from "vitest";
import { looksLikeCodexToml, parseTomlPaste } from "./pasteToml";

describe("looksLikeCodexToml", () => {
  test.each([
    ["[mcp_servers.docs]\ncommand = 'x'", true],
    ['  [mcp_servers."quoted name"]', true],
    ["[mcp_servers]\ndocs = { command = 'x' }", true],
    ["[other]\nx = 1", false],
    ["npx -y x", false],
  ])("%j -> %s", (text, want) => {
    expect(looksLikeCodexToml(text)).toBe(want);
  });
});

describe("parseTomlPaste", () => {
  test("a table with an env sub-table", () => {
    const r = parseTomlPaste(
      [
        "[mcp_servers.docs]",
        'command = "uvx"',
        'args = ["docs-search-mcp", "--root", "/srv/docs"]',
        "",
        "[mcp_servers.docs.env]",
        'DOCS_API_KEY = "abc"',
        'LOG_LEVEL = "info"',
      ].join("\n"),
    );
    expect(r).toEqual({
      kind: "servers",
      source: "toml",
      servers: [
        {
          name: "docs",
          transportType: "stdio",
          command: "uvx",
          args: ["docs-search-mcp", "--root", "/srv/docs"],
          url: "",
          env: [
            { key: "DOCS_API_KEY", value: "abc", isSecret: true },
            { key: "LOG_LEVEL", value: "info", isSecret: false },
          ],
        },
      ],
    });
  });

  test("the inline-table env form, and several servers", () => {
    const r = parseTomlPaste(
      [
        "[mcp_servers.docs]",
        'command = "npx"',
        'args = ["-y", "docs-mcp"]',
        'env = { DOCS_URL = "https://d", SLACK = "xoxb-123" }',
        "[mcp_servers.linear]",
        'url = "https://mcp.linear.app/mcp"',
      ].join("\n"),
    );
    expect(r.kind).toBe("servers");
    if (r.kind !== "servers") return;
    expect(r.servers.map((s) => [s.name, s.transportType])).toEqual([
      ["docs", "stdio"],
      ["linear", "http"],
    ]);
    expect(r.servers[0].env).toEqual([
      { key: "DOCS_URL", value: "https://d", isSecret: false },
      { key: "SLACK", value: "xoxb-123", isSecret: true },
    ]);
  });

  test("http_headers become headers; bearer_token_env_var adds an empty secret Authorization", () => {
    const r = parseTomlPaste(
      [
        "[mcp_servers.api]",
        'url = "https://example.com/mcp"',
        'bearer_token_env_var = "API_TOKEN"',
        'http_headers = { "X-Region" = "eu" }',
      ].join("\n"),
    );
    expect(r.kind === "servers" && r.servers[0].env).toEqual([
      { key: "X-Region", value: "eu", isSecret: false },
      { key: "Authorization", value: "", isSecret: true },
    ]);
  });

  test("a pasted Authorization header wins over bearer_token_env_var", () => {
    const r = parseTomlPaste(
      [
        "[mcp_servers.api]",
        'url = "https://example.com/mcp"',
        'bearer_token_env_var = "API_TOKEN"',
        "[mcp_servers.api.http_headers]",
        'Authorization = "Bearer abc"',
      ].join("\n"),
    );
    expect(r.kind === "servers" && r.servers[0].env).toEqual([
      { key: "Authorization", value: "Bearer abc", isSecret: true },
    ]);
  });

  test.each([
    ['[mcp_servers.docs]\ncommand = "npx"\nargs = [', "errInvalidToml", { line: "3" }],
    ["[mcp_servers.docs]\nenabled = true", "errBadServer", { name: "docs" }],
    ["[mcp_servers.docs]\ncommand = 'x'\nenv = 'A=1'", "errEnvNotObject", { name: "docs" }],
    [
      "[mcp_servers.docs]\ncommand = 'x'\nenv = { PORT = 1 }",
      "errBadEnvValue",
      { name: "docs", key: "PORT" },
    ],
    ["[mcp_servers]", "errNoServers", undefined],
    ["[mcp_servers]\ndocs = 1", "errBadServer", { name: "docs" }],
  ])("refuses %j with %s", (text, errorKey, params) => {
    const r = parseTomlPaste(text);
    expect(r.kind).toBe("unreadable");
    if (r.kind !== "unreadable") return;
    expect(r.errorKey).toBe(errorKey);
    if (params) expect(r.errorParams).toMatchObject(params);
  });
});
