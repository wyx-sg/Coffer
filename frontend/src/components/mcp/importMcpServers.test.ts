// frontend/src/components/mcp/importMcpServers.test.ts
//
// The add batch's outcomes, one per server: registered (then its secrets, then
// its reach), refused (a 409 flagged as a name clash), or rolled back when a
// secret could not be stored. It never rejects — the dialog renders the report.
import { beforeEach, describe, expect, test, vi } from "vitest";

import { getApiClient } from "@/lib/api/client";
import { scopeApi } from "@/lib/api/scope";
import { mockApiClient } from "@/test/mockApiClient";
import { importMcpServers, missingSecretValues, type NewServer } from "./importMcpServers";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { put: vi.fn() } }));

const t = ((key: string) => key) as never;

function server(name: string, over: Partial<NewServer> = {}): NewServer {
  return { name, transportType: "stdio", command: "npx", args: [], url: "", env: [], ...over };
}

beforeEach(() => vi.clearAllMocks());

describe("importMcpServers", () => {
  test("sends the title with the registration and writes a restricted reach after it", async () => {
    const api = mockApiClient({
      POST: vi.fn().mockResolvedValue({ data: { uid: "u-gh" }, error: undefined }),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [server("github", { title: "GitHub" })],
      created: new Map(),
      reach: { mode: "restricted", agents: ["a-1"] },
      t,
    });
    expect(api.POST.mock.calls[0][1]).toMatchObject({
      body: { kind: "mcp_server", name: "github", title: "GitHub" },
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

  test("a secret that cannot be stored rolls the registration back", async () => {
    const api = mockApiClient({
      POST: vi.fn((path: string) =>
        Promise.resolve(
          path === "/credentials"
            ? { data: undefined, error: { error: { code: "VAULT_LOCKED", message: "locked" } } }
            : { data: { uid: "u-a" }, error: undefined },
        ),
      ),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [server("a", { env: [{ key: "TOKEN", value: "x", isSecret: true }] })],
      created: new Map(),
      t,
    });
    expect(api.DELETE).toHaveBeenCalledWith("/resources/{uid}", {
      params: { path: { uid: "u-a" } },
    });
    expect(report.created).toEqual([]);
    expect(report.failed[0]).toMatchObject({ name: "a", nameTaken: false });
  });

  test("a 202 from the credential store marks the server as waiting for approval", async () => {
    const api = mockApiClient({
      POST: vi.fn((path: string) =>
        Promise.resolve(
          path === "/credentials"
            ? { data: { approval: { id: "ap" } }, error: undefined }
            : { data: { uid: "u-a" }, error: undefined },
        ),
      ),
    });
    vi.mocked(getApiClient).mockReturnValue(api as never);
    const report = await importMcpServers({
      servers: [server("a", { env: [{ key: "TOKEN", value: "x", isSecret: true }] })],
      created: new Map(),
      t,
    });
    expect(report.awaitingApproval).toEqual(["a"]);
  });

  test("missingSecretValues names the secrets still without a value", () => {
    expect(
      missingSecretValues(
        server("a", {
          env: [
            { key: "Authorization", value: "", isSecret: true },
            { key: "X", value: "", isSecret: false },
          ],
        }),
      ),
    ).toEqual(["Authorization"]);
  });
});
