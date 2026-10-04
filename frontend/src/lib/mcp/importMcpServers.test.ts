// frontend/src/lib/mcp/importMcpServers.test.ts
//
// The add batch's outcomes, one per server: registered (its secrets stored
// first, then its reach), refused (a 409 flagged as a name clash, the secrets it
// stored removed again), or not registered at all when a secret could not be
// stored. It never rejects — the dialog renders the report.
import { beforeEach, describe, expect, test, vi } from "vitest";

import { getApiClient } from "@/lib/api/client";
import { scopeApi } from "@/lib/api/scope";
import { mockApiClient } from "@/test/mockApiClient";
import { importMcpServers, missingSecretValues, type NewServer } from "@/lib/mcp/importMcpServers";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { put: vi.fn() } }));

const t = ((key: string) => key) as never;

function server(name: string, over: Partial<NewServer> = {}): NewServer {
  return { name, transportType: "stdio", command: "npx", args: [], url: "", env: [], ...over };
}

beforeEach(() => vi.clearAllMocks());

describe("importMcpServers", () => {
  test("sends the description with the registration and writes a restricted reach after it", async () => {
    const api = mockApiClient({
      POST: vi.fn().mockResolvedValue({ data: { uid: "u-gh" }, error: undefined }),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [server("github", { description: "GitHub" })],
      created: new Map(),
      reach: { mode: "restricted", agents: ["a-1"] },
      t,
    });
    expect(api.POST.mock.calls[0][1]).toMatchObject({
      body: { kind: "mcp_server", name: "github", description: "GitHub" },
    });
    expect(scopeApi.put).toHaveBeenCalledWith("u-gh", { agents: ["a-1"] });
    expect(report.created).toEqual([{ name: "github", uid: "u-gh" }]);
  });

  test("a 409 is reported as a name clash, and the rest of the batch still goes", async () => {
    const api = mockApiClient({
      POST: vi
        .fn()
        .mockResolvedValueOnce({
          data: undefined,
          error: { error: { code: "RESOURCE_ALREADY_EXISTS", message: "exists" } },
          response: new Response(null, { status: 409 }),
        })
        .mockResolvedValue({ data: { uid: "u-b" }, error: undefined }),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [server("a"), server("b")],
      created: new Map(),
      t,
    });
    expect(report.failed).toEqual([{ name: "a", message: expect.any(String), nameTaken: true }]);
    expect(report.created).toEqual([{ name: "b", uid: "u-b" }]);
  });

  test("a secret that cannot be stored registers nothing", async () => {
    const api = mockApiClient({
      POST: vi.fn((path: string) =>
        Promise.resolve(
          path === "/secrets"
            ? {
                data: undefined,
                error: { error: { code: "VAULT_LOCKED", message: "locked" } },
                response: new Response(null, { status: 423 }),
              }
            : { data: { uid: "u-a" }, error: undefined },
        ),
      ),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [
        server("a", { env: [{ key: "TOKEN", value: { kind: "new", name: "token", value: "x" } }] }),
      ],
      created: new Map(),
      t,
    });
    expect(api.POST.mock.calls.map((c) => c[0])).toEqual(["/secrets"]);
    expect(report.created).toEqual([]);
    expect(report.failed[0]).toMatchObject({ name: "a", nameTaken: false });
  });

  test("a chosen secret is cited as secret/<name>, a new one is stored first under that name", async () => {
    const api = mockApiClient({
      POST: vi.fn().mockResolvedValue({ data: { uid: "u-a" }, error: undefined }),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    await importMcpServers({
      servers: [
        server("a", {
          env: [
            { key: "TOKEN", value: { kind: "new", name: "a-token", value: "ghp_x" } },
            { key: "OTHER", value: { kind: "stored", name: "shared" } },
            { key: "LOG", value: { kind: "plain", value: "debug" } },
          ],
        }),
      ],
      created: new Map(),
      t,
    });
    expect(api.POST.mock.calls[0]).toEqual([
      "/secrets",
      { body: { ref: "secret/a-token", value: "ghp_x" } },
    ]);
    const body = (api.POST.mock.calls[1][1] as { body: { config: { transport: unknown } } }).body;
    expect(body.config.transport).toMatchObject({
      env: { LOG: "debug" },
      secret_refs: { TOKEN: "secret/a-token", OTHER: "secret/shared" },
    });
  });

  test("a registration that fails removes the secrets it stored first", async () => {
    const api = mockApiClient({
      POST: vi.fn((path: string) =>
        Promise.resolve(
          path === "/secrets"
            ? { data: undefined, error: undefined }
            : {
                data: undefined,
                error: { error: { code: "RESOURCE_ALREADY_EXISTS", message: "exists" } },
                response: new Response(null, { status: 409 }),
              },
        ),
      ),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [
        server("a", { env: [{ key: "TOKEN", value: { kind: "new", name: "token", value: "x" } }] }),
      ],
      created: new Map(),
      t,
    });
    const stored = (api.POST.mock.calls[0][1] as { body: { ref: string } }).body.ref;
    expect(stored).toBe("secret/token");
    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: stored } },
    });
    expect(report.failed[0]).toMatchObject({ name: "a", nameTaken: true });
  });

  test("a rollback delete the daemon refuses is logged, and the registration failure is still the report", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const api = mockApiClient({
      POST: vi.fn((path: string, init?: unknown) =>
        Promise.resolve(
          path === "/resources" && (init as { body: { name: string } }).body.name === "a"
            ? {
                data: undefined,
                error: { error: { code: "INTERNAL_ERROR", message: "boom" } },
                response: new Response(null, { status: 500 }),
              }
            : path === "/secrets"
              ? { data: undefined, error: undefined }
              : { data: { uid: "u-b" }, error: undefined },
        ),
      ),
      DELETE: vi.fn().mockResolvedValue({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "boom" } },
        response: new Response(null, { status: 500 }),
      }),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [
        server("a", { env: [{ key: "TOKEN", value: { kind: "new", name: "token", value: "x" } }] }),
        server("b"),
      ],
      created: new Map(),
      t,
    });
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining("rollback delete failed"),
      expect.anything(),
    );
    expect(report.failed).toHaveLength(1);
    expect(report.created.map((c) => c.name)).toEqual(["b"]);
    warn.mockRestore();
  });

  test("a binding the daemon holds for approval marks the server as waiting", async () => {
    const api = mockApiClient({
      POST: vi.fn().mockResolvedValue({ data: { uid: "u-a" }, error: undefined }),
      GET: vi.fn().mockResolvedValue({
        data: {
          approvals: [{ id: "ap", op: "bind", destination_uid: "u-a", ref: "secret/gh-token" }],
        },
        error: undefined,
      }),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [
        server("a", { env: [{ key: "TOKEN", value: { kind: "stored", name: "gh-token" } }] }),
      ],
      created: new Map(),
      t,
    });
    expect(report.awaitingApproval).toEqual([{ name: "a", secrets: ["TOKEN"] }]);
  });

  test("missingSecretValues names the secrets still without a value", () => {
    expect(
      missingSecretValues(
        server("a", {
          env: [
            { key: "Authorization", value: { kind: "new", name: "authorization", value: "" } },
            { key: "X", value: { kind: "plain", value: "" } },
          ],
        }),
      ),
    ).toEqual(["Authorization"]);
  });
});
