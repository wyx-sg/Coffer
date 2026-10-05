import { describe, expect, test } from "vitest";
import { parseCommandPaste } from "./pasteCommand";
import type { ParsedServer } from "./pasteTypes";

function one(text: string): ParsedServer {
  const r = parseCommandPaste(text);
  if (r?.kind !== "servers") throw new Error(`expected a server, got ${JSON.stringify(r)}`);
  expect(r.source).toBe("command");
  expect(r.servers).toHaveLength(1);
  return r.servers[0];
}

describe("parseCommandPaste — claude mcp add", () => {
  test("name, -e env and the command after --", () => {
    expect(
      one(
        "claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github",
      ),
    ).toEqual({
      name: "github",
      transportType: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-github"],
      url: "",
      env: [{ key: "GITHUB_TOKEN", value: "ghp_x", isSecret: true }],
    });
  });

  test("options before the name, variadic -e, a scope, and no --", () => {
    const s = one("claude mcp add -s user --env A=1 B=two airtable npx -y airtable-mcp-server");
    expect([s.name, s.command, s.args]).toEqual(["airtable", "npx", ["-y", "airtable-mcp-server"]]);
    expect(s.env.map((e) => [e.key, e.value])).toEqual([
      ["A", "1"],
      ["B", "two"],
    ]);
  });

  test("--transport http with headers, options after the URL", () => {
    const s = one(
      'claude mcp add --transport http sentry https://mcp.sentry.dev/mcp -H "Authorization: Bearer abc" --header "X-Org: acme"',
    );
    expect(s).toEqual({
      name: "sentry",
      transportType: "http",
      command: "",
      args: [],
      url: "https://mcp.sentry.dev/mcp",
      env: [
        { key: "Authorization", value: "abc", isSecret: true, scheme: "Bearer" },
        { key: "X-Org", value: "acme", isSecret: false },
      ],
    });
  });

  test("-t sse is read as Streamable HTTP", () => {
    const s = one("claude mcp add -t sse linear https://mcp.linear.app/sse");
    expect([s.transportType, s.url]).toEqual(["http", "https://mcp.linear.app/sse"]);
  });

  test("a continued line", () => {
    const s = one("claude mcp add docs \\\n  -e DOCS_KEY=abc \\\n  -- uvx docs-search-mcp");
    expect([s.name, s.command, s.args, s.env[0].isSecret]).toEqual([
      "docs",
      "uvx",
      ["docs-search-mcp"],
      true,
    ]);
  });

  test("add-json", () => {
    const s = one(
      `claude mcp add-json weather '{"type":"stdio","command":"node","args":["w.js"],"env":{"API_KEY":"k"}}'`,
    );
    expect([s.name, s.command, s.args, s.env]).toEqual([
      "weather",
      "node",
      ["w.js"],
      [{ key: "API_KEY", value: "k", isSecret: true }],
    ]);
  });
});

describe("parseCommandPaste — codex mcp add", () => {
  test("--env and the command after --", () => {
    const s = one(
      "codex mcp add docs --env DOCS_TOKEN=t --env LEVEL=info -- uvx docs-search-mcp --root /srv",
    );
    expect([s.name, s.command, s.args]).toEqual([
      "docs",
      "uvx",
      ["docs-search-mcp", "--root", "/srv"],
    ]);
    expect(s.env.map((e) => [e.key, e.isSecret])).toEqual([
      ["DOCS_TOKEN", true],
      ["LEVEL", false],
    ]);
  });

  test("--url with --bearer-token-env-var", () => {
    const s = one(
      "codex mcp add linear --url https://mcp.linear.app/mcp --bearer-token-env-var LINEAR_TOKEN",
    );
    expect([s.transportType, s.url, s.env]).toEqual([
      "http",
      "https://mcp.linear.app/mcp",
      [{ key: "Authorization", value: "", isSecret: true, scheme: "Bearer" }],
    ]);
  });
});

describe("parseCommandPaste — plain commands", () => {
  test.each([
    ["npx -y @modelcontextprotocol/server-github", "github", "npx"],
    ["npx -y @notionhq/notion-mcp-server", "notion", "npx"],
    ["uvx mcp-server-duckdb --db-path ~/data.db", "duckdb", "uvx"],
    ["bunx mcp-atlassian", "atlassian", "bunx"],
    ["pnpm dlx @x/server-files", "files", "pnpm"],
    ["docker run -i --rm -e GITHUB_TOKEN ghcr.io/github/github-mcp-server", "github", "docker"],
    ["node ./build/index.js", "index", "node"],
    ["python -m mcp_server_time", "time", "python"],
    ["uv run --directory /x weather.py", "weather", "uv"],
    ["/opt/bin/fs-server --root /", "fs-server", "/opt/bin/fs-server"],
    ["$ npx -y mcp-remote https://x", "remote", "npx"],
  ])("%j -> %s", (text, name, command) => {
    const s = one(text);
    expect([s.name, s.command, s.transportType]).toEqual([name, command, "stdio"]);
  });

  test("leading KEY=value assignments become env", () => {
    const s = one("GITHUB_TOKEN=ghp_abc LOG=debug npx -y @modelcontextprotocol/server-github");
    expect(s.env).toEqual([
      { key: "GITHUB_TOKEN", value: "ghp_abc", isSecret: true },
      { key: "LOG", value: "debug", isSecret: false },
    ]);
    expect(s.command).toBe("npx");
  });
});

describe("parseCommandPaste — not a command", () => {
  test.each([
    ["Install the server and restart Claude."],
    ["the server runs on node"],
    ["This server gives agents access to GitHub"],
    ["Run it with npx, then open the app"],
    ["What does this do?"],
    ["Hello world"],
    ["first\nsecond"],
  ])("%j is null", (text) => {
    expect(parseCommandPaste(text)).toBeNull();
  });

  test.each([
    ["claude mcp add", "errCommandNoName", { tool: "claude mcp add" }],
    ["claude mcp add github", "errCommandNoTarget", { tool: "claude mcp add" }],
    ["claude mcp add -t http api", "errCommandNoTarget", { tool: "claude mcp add" }],
    ["claude mcp add gh -e NOT_AN_ASSIGNMENT -- npx x", "errCommandOption", { flag: "-e" }],
    ["claude mcp add gh -e", "errCommandOption", { flag: "-e" }],
    ["claude mcp list", "errCommandNotAdd", { tool: "claude mcp list" }],
    ["claude mcp add-json w '{bad'", "errInvalidJson", undefined],
    [`npx -y "open`, "errCommandQuote", undefined],
  ])("%j -> %s", (text, errorKey, params) => {
    const r = parseCommandPaste(text);
    expect(r?.kind).toBe("unreadable");
    if (r?.kind !== "unreadable") return;
    expect(r.errorKey).toBe(errorKey);
    if (params) expect(r.errorParams).toEqual(params);
  });
});
