import { describe, expect, test } from "vitest";
import { describePaste, parsePaste, serverNameTooLong } from "./pasteParse";

describe("parsePaste — recognition", () => {
  test.each([
    ["", "empty"],
    ["   \n\t ", "empty"],
  ])("%j is empty", (text, kind) => {
    expect(parsePaste(text)).toEqual({ kind });
  });

  test("an mcpServers block with three servers", () => {
    const r = parsePaste(`
      { "mcpServers": {
          "notion": { "command": "npx", "args": ["-y", "@notionhq/notion-mcp-server"], "env": { "NOTION_TOKEN": "ntn_1" } },
          "figma": { "url": "https://mcp.figma.com/mcp" },
          "docs-search": { "command": "uvx", "args": ["docs-search-mcp"] } } }`);
    expect(r.kind === "servers" && r.source).toBe("json");
    if (r.kind !== "servers") return;
    expect(r.servers.map((s) => s.name)).toEqual(["notion", "figma", "docs-search"]);
    expect(r.servers[0].env).toEqual([{ key: "NOTION_TOKEN", value: "ntn_1", isSecret: true }]);
    expect(describePaste(r)).toEqual({
      key: "foundJson",
      params: { count: 3, names: "notion, figma, docs-search" },
    });
  });

  test("names are normalised with the pasted spelling kept; an over-long name is flagged, not cut", () => {
    const long = "internal-search-for-docs"; // 24
    const r = parsePaste(
      JSON.stringify({
        mcpServers: { "My Server": { command: "a" }, [`${long}-team`]: { command: "b" } },
      }),
    );
    if (r.kind !== "servers") throw new Error("expected servers");
    expect(r.servers[0]).toMatchObject({ name: "my-server", originalName: "My Server" });
    expect(r.servers[1].name).toHaveLength(29);
    expect(r.servers[1].originalName).toBeUndefined();
    expect(serverNameTooLong(r.servers[1].name)).toBe(true);
  });

  test("a 30-character key is flagged", () => {
    const key = "x".repeat(30);
    const r = parsePaste(JSON.stringify({ mcpServers: { [key]: { command: "a" } } }));
    expect(r.kind === "servers" && serverNameTooLong(r.servers[0].name)).toBe(true);
  });

  test("duplicate names within one paste are suffixed", () => {
    const r = parsePaste(
      JSON.stringify({ mcpServers: { Docs: { command: "a" }, docs: { command: "b" } } }),
    );
    expect(r.kind === "servers" && r.servers.map((s) => s.name)).toEqual(["docs", "docs-2"]);
  });

  test("a claude mcp add line", () => {
    const r = parsePaste(
      "claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github",
    );
    expect(r).toEqual({
      kind: "servers",
      source: "command",
      servers: [
        {
          name: "github",
          transportType: "stdio",
          command: "npx",
          args: ["-y", "@modelcontextprotocol/server-github"],
          url: "",
          env: [{ key: "GITHUB_TOKEN", value: "ghp_x", isSecret: true }],
        },
      ],
    });
    expect(describePaste(r)?.key).toBe("foundCommand");
  });

  test.each([
    ["https://mcp.example.com/mcp", "example"],
    ["  https://mcp.context7.com/mcp\n", "context7"],
    ["http://localhost:3000/mcp", "localhost"],
    ["https://mcp.example.com/mcp?token=abc", "example"],
  ])("the URL %j", (text, name) => {
    const r = parsePaste(text);
    expect(r).toEqual({
      kind: "servers",
      source: "url",
      servers: [{ name, transportType: "http", command: "", args: [], url: text.trim(), env: [] }],
    });
    expect(describePaste(r)?.key).toBe("foundUrl");
  });

  test.each([
    [
      [
        "[mcp_servers.docs]",
        'command = "uvx"',
        'args = ["docs-search-mcp"]',
        "[mcp_servers.docs.env]",
        'DOCS_TOKEN = "t"',
        'LEVEL = "info"',
      ],
    ],
    [
      [
        "[mcp_servers.docs]",
        'command = "uvx"',
        'args = ["docs-search-mcp"]',
        'env = { DOCS_TOKEN = "t", LEVEL = "info" }',
      ],
    ],
  ])("Codex TOML %#", (lines) => {
    const r = parsePaste(lines.join("\n"));
    expect(r).toEqual({
      kind: "servers",
      source: "toml",
      servers: [
        {
          name: "docs",
          transportType: "stdio",
          command: "uvx",
          args: ["docs-search-mcp"],
          url: "",
          env: [
            { key: "DOCS_TOKEN", value: "t", isSecret: true },
            { key: "LEVEL", value: "info", isSecret: false },
          ],
        },
      ],
    });
    expect(describePaste(r)).toEqual({ key: "foundToml", params: { count: 1, names: "docs" } });
  });

  test("a quoted TOML table name is normalised", () => {
    const r = parsePaste('[mcp_servers."Team Docs"]\ncommand = "x"');
    expect(r.kind === "servers" && r.servers[0]).toMatchObject({
      name: "team-docs",
      originalName: "Team Docs",
    });
  });
});

describe("parsePaste — unreadable input", () => {
  test.each([
    [
      '{ "mcpServers": { "a": { "command": "x", } } }',
      "errInvalidJson",
      ["line", "column", "detail"],
    ],
    ['{"mcpServers": []}', "errServersNotObject", ["key"]],
    ["[1,2]", "errNotAnObject", []],
    [
      '[mcp_servers.docs]\ncommand = "npx"\nargs = ["-y" "x"]',
      "errInvalidToml",
      ["line", "detail"],
    ],
    ["Install the server with npm, then restart your editor.", "errUnreadable", []],
    ["This MCP server lets your agent read GitHub issues", "errUnreadable", []],
    ["ftp://example.com/mcp", "errUnreadable", []],
  ])("%j -> %s", (text, errorKey, paramKeys) => {
    const r = parsePaste(text);
    expect(r.kind).toBe("unreadable");
    if (r.kind !== "unreadable") return;
    expect(r.errorKey).toBe(errorKey);
    expect(Object.keys(r.errorParams ?? {}).sort()).toEqual([...paramKeys].sort());
    expect(describePaste(r)).toEqual({ key: errorKey, params: r.errorParams ?? {} });
  });

  test("malformed TOML names its line", () => {
    const r = parsePaste('[mcp_servers.docs]\ncommand = "npx"\nargs = ["-y" "x"]');
    expect(r.kind === "unreadable" && r.errorParams?.line).toBe("3");
  });

  test("an empty box has no summary", () => {
    expect(describePaste({ kind: "empty" })).toBeNull();
  });
});
