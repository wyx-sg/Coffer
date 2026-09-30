import { describe, expect, test } from "vitest";
import { acceptance } from "@/test/acceptance";
import { jsonSyntaxError, parseJsonPaste } from "./pasteJson";

const json = (v: unknown) => JSON.stringify(v);

function servers(text: string) {
  const r = parseJsonPaste(text);
  if (r.kind !== "servers") throw new Error(`expected servers, got ${JSON.stringify(r)}`);
  expect(r.source).toBe("json");
  return r.servers;
}

function error(text: string) {
  const r = parseJsonPaste(text);
  if (r.kind !== "unreadable") throw new Error(`expected unreadable, got ${JSON.stringify(r)}`);
  return r;
}

describe("parseJsonPaste — shapes", () => {
  test("the standard mcpServers wrapper", () => {
    const [s] = servers(
      json({
        mcpServers: { filesystem: { command: "npx", args: ["-y", "@x/server-fs", "/tmp"] } },
      }),
    );
    expect(s).toEqual({
      name: "filesystem",
      transportType: "stdio",
      command: "npx",
      args: ["-y", "@x/server-fs", "/tmp"],
      url: "",
      env: [],
    });
  });

  test("the design's three-server block", () => {
    const list = servers(
      json({
        mcpServers: {
          notion: { command: "npx", args: ["-y", "@notionhq/notion-mcp-server"] },
          figma: { url: "https://mcp.figma.com/mcp" },
          "docs-search": { command: "uvx", args: ["docs-search-mcp"] },
        },
      }),
    );
    expect(list.map((s) => [s.name, s.transportType])).toEqual([
      ["notion", "stdio"],
      ["figma", "http"],
      ["docs-search", "stdio"],
    ]);
  });

  test.each([["servers"], ["mcp_servers"]])("the %s alias", (key) => {
    expect(servers(json({ [key]: { a: { command: "a" } } }))[0].name).toBe("a");
  });

  test("a bare name->config map", () => {
    expect(servers(json({ fs: { command: "npx" } }))[0].name).toBe("fs");
  });

  test.each([
    [{ command: "npx", args: ["-y", "@modelcontextprotocol/server-github"] }, "github", "stdio"],
    [{ url: "https://mcp.sentry.dev/mcp" }, "sentry", "http"],
    [{ type: "http", url: "https://mcp.example.com/mcp" }, "example", "http"],
    [{ type: "sse", url: "https://mcp.example.com/sse" }, "example", "http"],
    [{ serverUrl: "https://mcp.context7.com/mcp" }, "context7", "http"],
  ])("one server object %j is named from its package or host", (cfg, name, transport) => {
    const [s] = servers(json(cfg));
    expect([s.name, s.transportType]).toEqual([name, transport]);
  });

  test("an sse-marked entry is read as Streamable HTTP", () => {
    const [s] = servers(json({ mcpServers: { x: { type: "sse", url: "https://x.dev/sse" } } }));
    expect(s.transportType).toBe("http");
    expect(s.url).toBe("https://x.dev/sse");
  });

  test("secret-looking env vars are offered as secrets", () => {
    const [s] = servers(
      json({
        mcpServers: {
          gh: {
            command: "npx",
            env: { GITHUB_TOKEN: "ghp_x", NODE_ENV: "production", SLACK_URL: "xoxb-1" },
          },
        },
      }),
    );
    expect(s.env).toEqual([
      { key: "GITHUB_TOKEN", value: "ghp_x", isSecret: true },
      { key: "NODE_ENV", value: "production", isSecret: false },
      { key: "SLACK_URL", value: "xoxb-1", isSecret: true },
    ]);
  });

  acceptance("web-ui", "a pasted HTTP server's headers are reviewed for secrets", () => {
    const [s] = servers(
      json({
        mcpServers: {
          api: {
            url: "https://example.com/mcp",
            headers: { Authorization: "Bearer abc", "X-Region": "us-east" },
          },
        },
      }),
    );
    expect(s.env).toEqual([
      { key: "Authorization", value: "Bearer abc", isSecret: true },
      { key: "X-Region", value: "us-east", isSecret: false },
    ]);
  });

  test("an http server's env still travels as headers; a headers entry wins a clash", () => {
    const [s] = servers(
      json({
        mcpServers: {
          api: {
            url: "https://example.com/mcp",
            env: { REGION: "eu", TIER: "free" },
            headers: { REGION: "us" },
          },
        },
      }),
    );
    expect(s.env.map((e) => [e.key, e.value])).toEqual([
      ["TIER", "free"],
      ["REGION", "us"],
    ]);
  });
});

describe("parseJsonPaste — errors", () => {
  test("malformed JSON carries the line and column", () => {
    const r = error('{\n  "mcpServers": {\n    "a": { command: "x" }\n  }\n}');
    expect(r.errorKey).toBe("errInvalidJson");
    expect(r.errorParams).toMatchObject({ line: "3", column: "12" });
    expect(r.errorParams?.detail).not.toMatch(/position|line \d/);
  });

  test.each([
    [
      "Unexpected token n in JSON at position 1",
      "{nope",
      { line: "1", column: "2", detail: "Unexpected token n" },
    ],
    [
      "Expected ',' or '}' after property value in JSON at position 9 (line 2 column 3)",
      "",
      { line: "2", column: "3", detail: "Expected ',' or '}' after property value" },
    ],
    [
      "JSON.parse: expected property name or '}' at line 1 column 2 of the JSON data",
      "",
      { line: "1", column: "2", detail: "expected property name or '}'" },
    ],
  ])("reads the engine message %j", (message, text, params) => {
    expect(jsonSyntaxError(text, new SyntaxError(message))).toEqual({
      kind: "unreadable",
      errorKey: "errInvalidJson",
      errorParams: params,
    });
  });

  test("an engine message with no location", () => {
    expect(jsonSyntaxError("{", new SyntaxError("JSON Parse error: Expected '}'"))).toEqual({
      kind: "unreadable",
      errorKey: "errInvalidJsonNoLocation",
      errorParams: { detail: "Expected '}'" },
    });
  });

  test.each([
    ["[1,2]", "errNotAnObject", undefined],
    ['"just a string"', "errNotAnObject", undefined],
    [json({ mcpServers: [] }), "errServersNotObject", { key: "mcpServers" }],
    [json({ servers: "x" }), "errServersNotObject", { key: "servers" }],
    [json({ mcpServers: {} }), "errNoServers", undefined],
    ["{}", "errNoServers", undefined],
    [json({ mcpServers: { broken: { foo: 1 } } }), "errBadServer", { name: "broken" }],
    [json({ broken: 1 }), "errBadServer", { name: "broken" }],
    [
      json({ mcpServers: { fs: { command: "npx", env: "API_KEY=x" } } }),
      "errEnvNotObject",
      { name: "fs" },
    ],
    [
      json({ mcpServers: { fs: { command: "npx", env: { CONFIG: { nested: "o" } } } } }),
      "errBadEnvValue",
      { name: "fs", key: "CONFIG" },
    ],
    [
      json({ mcpServers: { fs: { command: "npx", env: { PORT: 8080 } } } }),
      "errBadEnvValue",
      { name: "fs", key: "PORT" },
    ],
    [
      json({ mcpServers: { api: { url: "https://x/mcp", headers: "Auth: x" } } }),
      "errHeadersNotObject",
      { name: "api" },
    ],
    [
      json({ mcpServers: { api: { url: "https://x/mcp", headers: { "X-N": 1 } } } }),
      "errBadHeaderValue",
      { name: "api", key: "X-N" },
    ],
  ])("%s -> %s", (text, errorKey, errorParams) => {
    const r = error(text);
    expect(r.errorKey).toBe(errorKey);
    expect(r.errorParams).toEqual(errorParams);
  });
});
