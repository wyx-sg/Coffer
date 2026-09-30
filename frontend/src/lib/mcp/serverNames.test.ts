import { describe, expect, test } from "vitest";
import {
  MCP_SERVER_NAME_MAX,
  finaliseNames,
  isValidServerName,
  nameFromCommand,
  nameFromPackage,
  nameFromUrl,
  normaliseServerName,
  serverNameTooLong,
} from "./serverNames";
import type { ParsedServer } from "./pasteTypes";

describe("normaliseServerName", () => {
  test.each([
    ["My Server", "my-server"],
    ["github", "github"],
    ["docs.search", "docs.search"],
    ["  Hello, World!  ", "hello-world"],
    ["a - b", "a-b"],
    ["weird__name", "weird_name"],
    ["--x--", "x"],
    ["日本", "server"],
    ["", "server"],
  ])("%j -> %j", (raw, want) => {
    expect(normaliseServerName(raw)).toBe(want);
    expect(isValidServerName(normaliseServerName(raw))).toBe(true);
  });
});

describe("isValidServerName / serverNameTooLong", () => {
  test("allows the 24-character cap and flags anything longer", () => {
    expect(MCP_SERVER_NAME_MAX).toBe(24);
    expect(serverNameTooLong("x".repeat(24))).toBe(false);
    expect(serverNameTooLong("x".repeat(25))).toBe(true);
    expect(isValidServerName("x".repeat(24))).toBe(true);
    expect(isValidServerName("x".repeat(25))).toBe(false);
  });

  test.each([["has space"], ["a__b"], [""], ["slash/name"]])("rejects %j", (name) => {
    expect(isValidServerName(name)).toBe(false);
  });
});

describe("nameFromPackage", () => {
  test.each([
    ["@modelcontextprotocol/server-github", "github"],
    ["@notionhq/notion-mcp-server", "notion"],
    ["mcp-atlassian", "atlassian"],
    ["mcp-server-duckdb", "duckdb"],
    ["docs-search-mcp", "docs-search"],
    ["@upstash/context7-mcp@latest", "context7"],
    ["mcp-server-fetch==1.2", "fetch"],
    ["mcp", "mcp"],
  ])("%j -> %j", (pkg, want) => {
    expect(nameFromPackage(pkg)).toBe(want);
  });
});

describe("nameFromCommand", () => {
  test.each([
    ["npx", ["-y", "@modelcontextprotocol/server-github"], "github"],
    ["npx", ["-p", "other", "@notionhq/notion-mcp-server"], "notion"],
    ["uvx", ["mcp-server-duckdb", "--db", "x.db"], "duckdb"],
    ["uvx", ["--from", "git+https://x", "mcp-atlassian"], "atlassian"],
    ["bunx", ["mcp-atlassian"], "atlassian"],
    ["pnpm", ["dlx", "@x/server-foo"], "foo"],
    [
      "docker",
      ["run", "-i", "--rm", "-e", "TOKEN", "ghcr.io/github/github-mcp-server:1.0"],
      "github",
    ],
    ["docker", ["run", "mcp/fetch"], "fetch"],
    ["python", ["-m", "mcp_server_git"], "git"],
    ["node", ["/opt/weather/dist/index.js"], "weather"],
    ["node", ["./tools/search.js"], "search"],
    ["uv", ["run", "--with", "x", "server.py"], "server"],
    ["/usr/local/bin/my-tool", [], "my-tool"],
  ])("%s %j -> %j", (command, args, want) => {
    expect(nameFromCommand(command, args)).toBe(want);
  });
});

describe("nameFromUrl", () => {
  test.each([
    ["https://mcp.example.com/mcp", "example"],
    ["https://mcp.context7.com/mcp", "context7"],
    ["https://mcp.sentry.dev/mcp", "sentry"],
    ["http://localhost:3000/mcp", "localhost"],
    ["https://api.githubcopilot.com/mcp/", "githubcopilot"],
    ["https://www.example.co.uk/mcp", "example"],
    ["http://127.0.0.1:8080/mcp", "127.0.0.1"],
  ])("%j -> %j", (url, want) => {
    expect(nameFromUrl(url)).toBe(want);
  });
});

describe("finaliseNames", () => {
  const server = (name: string): ParsedServer => ({
    name,
    transportType: "stdio",
    command: "x",
    args: [],
    url: "",
    env: [],
  });

  test("normalises, records the pasted spelling, and suffixes duplicates", () => {
    const out = finaliseNames([
      server("My Server"),
      server("my-server"),
      server("github"),
      server("github"),
    ]);
    expect(out.map((s) => [s.name, s.originalName])).toEqual([
      ["my-server", "My Server"],
      ["my-server-2", "my-server"],
      ["github", undefined],
      ["github-2", "github"],
    ]);
    expect("originalName" in out[2]).toBe(false);
  });
});
