// frontend/src/lib/mcp/editMcpServerSave.test.ts
//
// The save path's dealings with secrets: a chosen secret is cited as
// `secret/<name>`, a new one is written to Secrets before the PATCH (and removed
// again when the PATCH fails), a secret Coffer minted for the server keeps its
// ref while it is still chosen, and which no-longer-cited refs may be deleted.
// A ref is "its own" when it is named for this server (`mcp_server/<name>/…`).
import { beforeEach, describe, expect, test, vi } from "vitest";

import { getApiClient } from "@/lib/api/client";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { configTextFrom, saveMcpServerEdit } from "@/lib/mcp/editMcpServerSave";
import type { KeyValueSecretRow } from "@/lib/secretValue";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));

const t = ((key: string) => key) as never;

/** A ref as `lib/secretRef.ts` mints one. */
const MINTED = "mcp_server/github/GITHUB_TOKEN";
/** One the user typed, or pasted in to share a secret with another server. */
const HAND_WRITTEN = "shared/github-token";

function resource(overrides: Record<string, unknown> = {}) {
  return {
    uid: "u-github",
    kind: "mcp_server",
    name: "github",
    description: null,
    config: {
      transport: {
        type: "stdio",
        command: "npx",
        args: [],
        env: {},
        secret_refs: { GITHUB_TOKEN: MINTED },
      },
    },
    ...overrides,
  } as never;
}

/** A row as the dialog loads it: choosing the secret Coffer minted for the key. */
function row(over: Partial<KeyValueSecretRow> = {}): KeyValueSecretRow {
  return { key: "GITHUB_TOKEN", value: { kind: "stored", name: "GITHUB_TOKEN" }, ...over };
}

async function save(rows: KeyValueSecretRow[], res = resource()) {
  return saveMcpServerEdit({
    resource: res,
    description: "",
    configText: JSON.stringify({ transport: { type: "stdio", command: "npx", args: [] } }),
    rows,
    timeouts: { spawn: 30, request: 120 },
    t,
  });
}

let api: ApiClientMock;

beforeEach(() => {
  api = mockApiClient();
  vi.mocked(getApiClient).mockReturnValue(api as never);
});

describe("which address a secret is cited by", () => {
  test("a stored secret is cited as secret/<name> and nothing is written", async () => {
    await save([row({ value: { kind: "stored", name: "github-pat" } })]);

    expect(api.POST).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: "secret/github-pat" });
    // The server's own minted secret is no longer cited, so it is released.
    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });

  test("the secret Coffer minted for the key keeps its ref while it stays chosen", async () => {
    await save([row()]);

    expect(api.POST).not.toHaveBeenCalled();
    expect(api.DELETE).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED });
  });

  test("a new secret is written to Secrets before the PATCH and cited by name", async () => {
    await save([row({ value: { kind: "new", name: "gh-token", value: "ghp_new" } })]);

    expect(api.POST).toHaveBeenCalledWith("/secrets", {
      body: { ref: "secret/gh-token", value: "ghp_new" },
    });
    expect(api.POST.mock.invocationCallOrder[0]).toBeLessThan(
      api.PATCH.mock.invocationCallOrder[0],
    );
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: "secret/gh-token" });
  });

  test("a new secret is removed again when the PATCH is rejected", async () => {
    api.PATCH.mockResolvedValue({
      data: undefined,
      error: { error: { code: "CONFIG_INVALID", message: "bad" } },
      response: new Response(null, { status: 422 }),
    } as never);
    await expect(
      save([row({ value: { kind: "new", name: "gh-token", value: "ghp_new" } })]),
    ).rejects.toBeDefined();

    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: "secret/gh-token" } },
    });
  });

  test("a new secret with no value is refused before anything is written", async () => {
    await expect(
      save([{ key: "NEW", value: { kind: "new", name: "new", value: "" } }]),
    ).rejects.toThrow("mcp.edit.errSecretNeedsValue");
    expect(api.POST).not.toHaveBeenCalled();
    expect(api.PATCH).not.toHaveBeenCalled();
  });

  test("a row switched to plain drops its ref and keeps the value in env", async () => {
    await save([row({ value: { kind: "plain", value: "public" } })]);

    expect(patchedRefs()).toEqual({});
    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });
});

describe("which no-longer-cited refs may be deleted", () => {
  test("a minted ref this server dropped is deleted", async () => {
    await save([]);

    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });

  test("a hand-written or shared ref is never deleted", async () => {
    const shared = resource({
      config: { transport: { type: "stdio", secret_refs: { GITHUB_TOKEN: HAND_WRITTEN } } },
    });
    await save([], shared);

    expect(api.DELETE).not.toHaveBeenCalled();
  });
});

function patchedRefs(): Record<string, string> {
  const body = api.PATCH.mock.calls[0][1] as {
    body: { config: { transport: { secret_refs: Record<string, string> } } };
  };
  return body.body.config.transport.secret_refs;
}

describe("configTextFrom", () => {
  test("only plain rows land in env, and the working directory is written or cleared", () => {
    const stored = { transport: { type: "stdio", command: "npx", cwd: "/old", extra: 1 } };
    const form = {
      type: "stdio" as const,
      url: "",
      command: "npx",
      args: ["-y", "x"],
      rows: [row(), { key: "LOG_LEVEL", value: { kind: "plain" as const, value: "debug" } }],
    };
    const withCwd = JSON.parse(configTextFrom(stored, { ...form, cwd: " ~/src " }));
    expect(withCwd.transport).toEqual({
      type: "stdio",
      command: "npx",
      args: ["-y", "x"],
      env: { LOG_LEVEL: "debug" },
      cwd: "~/src",
      extra: 1,
    });
    const cleared = JSON.parse(configTextFrom(stored, { ...form, cwd: "" }));
    expect(cleared.transport).not.toHaveProperty("cwd");
  });
});
