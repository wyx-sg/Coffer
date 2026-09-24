// frontend/src/components/mcp/jsonImport.test.ts
import { describe, expect, test } from "vitest";
import { acceptance } from "@/test/acceptance";
import { parseMcpJson } from "./jsonImport";

describe("parseMcpJson", () => {
  test("parses the standard mcpServers wrapper", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: {
          filesystem: {
            command: "npx",
            args: ["-y", "@x/server-fs", "/tmp"],
          },
        },
      }),
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.servers).toHaveLength(1);
    const s = r.servers[0];
    expect(s.name).toBe("filesystem");
    expect(s.transportType).toBe("stdio");
    expect(s.command).toBe("npx");
    expect(s.args).toEqual(["-y", "@x/server-fs", "/tmp"]);
  });

  test("parses multiple servers as a batch", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: {
          a: { command: "a" },
          b: { url: "https://b.example.com/mcp" },
        },
      }),
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.servers.map((s) => s.name)).toEqual(["a", "b"]);
    expect(r.servers[1].transportType).toBe("http");
    expect(r.servers[1].url).toBe("https://b.example.com/mcp");
  });

  test("accepts a bare name->config map (no mcpServers wrapper)", () => {
    const r = parseMcpJson(JSON.stringify({ fs: { command: "npx" } }));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.servers[0].name).toBe("fs");
  });

  test("marks secret-looking env vars by heuristic", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: {
          gh: {
            command: "npx",
            env: { GITHUB_TOKEN: "ghp_x", NODE_ENV: "production" },
          },
        },
      }),
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    const env = r.servers[0].env;
    expect(env.find((e) => e.key === "GITHUB_TOKEN")?.isSecret).toBe(true);
    expect(env.find((e) => e.key === "GITHUB_TOKEN")?.value).toBe("ghp_x");
    expect(env.find((e) => e.key === "NODE_ENV")?.isSecret).toBe(false);
  });

  test("rejects invalid JSON", () => {
    const r = parseMcpJson("{not json");
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.errorKey).toBe("errInvalidJson");
  });

  test("rejects a name-less bare config", () => {
    const r = parseMcpJson(JSON.stringify({ command: "npx", args: [] }));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.errorKey).toBe("errNoServers");
  });

  test("flags a server missing both command and url", () => {
    const r = parseMcpJson(JSON.stringify({ mcpServers: { broken: { foo: 1 } } }));
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.errorKey).toBe("errBadServer");
    expect(r.errorParams?.name).toBe("broken");
  });

  test("rejects non-string env values (object) instead of stringifying to [object Object]", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: {
          fs: {
            command: "npx",
            env: { CONFIG: { nested: "object" } },
          },
        },
      }),
    );
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.errorKey).toBe("errBadEnvValue");
    expect(r.errorParams?.name).toBe("fs");
    expect(r.errorParams?.key).toBe("CONFIG");
  });

  test("rejects numeric env values", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: { fs: { command: "npx", env: { PORT: 8080 } } },
      }),
    );
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.errorKey).toBe("errBadEnvValue");
    expect(r.errorParams?.key).toBe("PORT");
  });

  acceptance("web-ui", "a pasted HTTP server's headers are reviewed for secrets", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: {
          api: {
            url: "https://example.com/mcp",
            headers: { Authorization: "Bearer abc", "X-Region": "us-east" },
          },
        },
      }),
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.servers[0].env).toEqual([
      { key: "Authorization", value: "Bearer abc", isSecret: true },
      { key: "X-Region", value: "us-east", isSecret: false },
    ]);
  });

  test("an http server's env still travels as headers; a headers entry wins a clash", () => {
    const r = parseMcpJson(
      JSON.stringify({
        mcpServers: {
          api: {
            url: "https://example.com/mcp",
            env: { REGION: "eu", TIER: "free" },
            headers: { REGION: "us" },
          },
        },
      }),
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.servers[0].env.map((e) => [e.key, e.value])).toEqual([
      ["TIER", "free"],
      ["REGION", "us"],
    ]);
  });

  test("rejects a non-object headers block and a non-string header value", () => {
    const notObject = parseMcpJson(
      JSON.stringify({ mcpServers: { api: { url: "https://x/mcp", headers: "Auth: x" } } }),
    );
    expect(notObject.ok).toBe(false);
    if (notObject.ok) return;
    expect(notObject.errorKey).toBe("errHeadersNotObject");
    expect(notObject.errorParams).toEqual({ name: "api" });

    const badValue = parseMcpJson(
      JSON.stringify({ mcpServers: { api: { url: "https://x/mcp", headers: { "X-N": 1 } } } }),
    );
    expect(badValue.ok).toBe(false);
    if (badValue.ok) return;
    expect(badValue.errorKey).toBe("errBadHeaderValue");
    expect(badValue.errorParams).toEqual({ name: "api", key: "X-N" });
  });
});
