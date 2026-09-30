// frontend/src/components/mcp/editMcpServerSave.test.ts
//
// The save path's two dealings with secret refs: which address a secret is
// written to, and which no-longer-cited addresses may be deleted afterwards.
// Both used to read `resource.name` — refs were built as `<name>.<key>` and the
// cleanup owned whatever started with `<name>.` — so the tests here rename the
// server out from under its own refs, which is the state that became reachable
// when rename became a field on `PATCH /resources/{uid}` for every kind.
import { beforeEach, describe, expect, test, vi } from "vitest";

import { getApiClient } from "@/lib/api/client";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { configTextFrom, saveMcpServerEdit } from "./editMcpServerSave";
import type { ParsedEnvVar } from "@/lib/mcp/pasteTypes";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));

const t = ((key: string) => key) as never;

/** A ref as `lib/secretRef.ts` mints one. */
const MINTED = "mcp_server/0123456789abcdef0123456789abcdef/GITHUB_TOKEN";
/** One the user typed, or pasted in to share a secret with another server. */
const HAND_WRITTEN = "shared/github-token";

function resource(overrides: Record<string, unknown> = {}) {
  return {
    uid: "u-github",
    kind: "mcp_server",
    // The label has MOVED since the refs below were minted. Every assertion in
    // this file has to hold regardless of what it says.
    name: "github-renamed",
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

/** A Secret row as the dialog loads it: citing its own stored secret. */
function row(over: Partial<ParsedEnvVar> = {}): ParsedEnvVar {
  return {
    key: "GITHUB_TOKEN",
    value: "",
    isSecret: true,
    ref: MINTED,
    storedRef: MINTED,
    loadedKey: "GITHUB_TOKEN",
    ...over,
  };
}

async function save(rows: ParsedEnvVar[], res = resource()) {
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

describe("which address a secret is written to", () => {
  test("a rotation writes THROUGH the existing ref", async () => {
    // Minting here would move the secret, and a move crosses the sync remote as
    // a delete plus an add of something the other machine cannot place.
    await save([row({ ref: null, value: "ghp_new" })]);

    expect(api.POST).toHaveBeenCalledWith("/secrets", {
      body: { ref: MINTED, value: "ghp_new" },
    });
    expect(api.DELETE).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED });
  });

  test("a brand-new row gets an opaque ref, not one built from the server's name", async () => {
    await save([row(), { key: "EXTRA", value: "s3cret", isSecret: true }]);

    const written = (api.POST.mock.calls[0][1] as { body: { ref: string } }).body.ref;
    expect(written).toMatch(/^mcp_server\/[0-9a-f]{32}\/EXTRA$/);
    expect(written).not.toContain("github");
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED, EXTRA: written });
  });

  test("renaming the env key with a new value mints a new ref and releases the old", async () => {
    await save([row({ key: "GH_TOKEN", ref: null, value: "ghp_new" })]);

    const written = (api.POST.mock.calls[0][1] as { body: { ref: string } }).body.ref;
    expect(written).toMatch(/^mcp_server\/[0-9a-f]{32}\/GH_TOKEN$/);
    expect(patchedRefs()).toEqual({ GH_TOKEN: written });
    // The address the config left behind is one Coffer minted for this server,
    // so it goes — even though the server's name no longer resembles it.
    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });
});

describe("which no-longer-cited refs may be deleted", () => {
  test("a minted ref this server dropped is deleted after a rename", async () => {
    // The regression this replaces: with the old `<name>.` prefix test, a
    // renamed server owned none of its own refs and the cleanup silently did
    // nothing, leaving a secret in the store that nothing would ever cite.
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

  test("a ref the config still cites is left alone", async () => {
    await save([row()]);

    expect(api.DELETE).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED });
  });
});

test("renaming an env key without re-entering its value is refused", async () => {
  // Unchanged by the ref rework and asserted so it stays that way: the dialog
  // holds no plaintext, so it cannot re-address a secret it cannot rewrite.
  await expect(save([row({ key: "GH_TOKEN" })])).rejects.toThrow("mcp.edit.errRenameNeedsValue");
  expect(api.PATCH).not.toHaveBeenCalled();
});

function patchedRefs(): Record<string, string> {
  const body = api.PATCH.mock.calls[0][1] as {
    body: { config: { transport: { secret_refs: Record<string, string> } } };
  };
  return body.body.config.transport.secret_refs;
}

describe("a rotation that waits for approval", () => {
  test("a 202 answer is reported as saved and awaiting approval", async () => {
    // The daemon stores the replacement sealed and keeps sending the old value
    // until someone approves in the Coffer app; the save itself went through.
    api.POST.mockResolvedValue({ data: { approval: { id: "apr-1" } }, error: undefined });
    const out = await save([row({ ref: null, value: "ghp_new" })]);

    expect(out.awaitingApproval).toBe(true);
    expect(api.PATCH).toHaveBeenCalled();
  });

  test("a plain 204 store is not", async () => {
    const out = await save([row({ ref: null, value: "ghp_new" })]);

    expect(out.awaitingApproval).toBe(false);
  });
});

describe("the Secret | Plain row model", () => {
  test("a row citing a Secrets-page secret stores its ref and writes no value", async () => {
    await save([row({ ref: "secret/GITHUB_PAT" })]);

    expect(api.POST).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: "secret/GITHUB_PAT" });
    // The server's own minted secret is no longer cited, so it is released.
    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });

  test("a new value on a row loaded from a Secrets-page secret mints; never overwrites it", async () => {
    const shared = resource({
      config: {
        transport: { type: "stdio", secret_refs: { GITHUB_TOKEN: "secret/GITHUB_PAT" } },
      },
    });
    await save([row({ ref: null, storedRef: "secret/GITHUB_PAT", value: "ghp_mine" })], shared);

    const written = (api.POST.mock.calls[0][1] as { body: { ref: string } }).body.ref;
    expect(written).toMatch(/^mcp_server\/[0-9a-f]{32}\/GITHUB_TOKEN$/);
    expect(api.DELETE).not.toHaveBeenCalled();
  });

  test("Replace left blank keeps the stored secret", async () => {
    await save([row({ ref: null })]);

    expect(api.POST).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED });
  });

  test("a row switched to Plain drops its ref", async () => {
    await save([row({ isSecret: false, value: "public" })]);

    expect(patchedRefs()).toEqual({});
    expect(api.DELETE).toHaveBeenCalledWith("/secrets/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });

  test("a new Secret row with no value is refused before anything is written", async () => {
    await expect(save([{ key: "NEW", value: "", isSecret: true }])).rejects.toThrow(
      "mcp.edit.errSecretNeedsValue",
    );
    expect(api.POST).not.toHaveBeenCalled();
    expect(api.PATCH).not.toHaveBeenCalled();
  });

  test("renaming a row that cites a Secrets-page secret needs no value", async () => {
    await save([row({ key: "GH", ref: "secret/GITHUB_PAT", storedRef: "secret/GITHUB_PAT" })]);

    expect(patchedRefs()).toEqual({ GH: "secret/GITHUB_PAT" });
  });
});

describe("configTextFrom", () => {
  test("only Plain rows land in env, and the working directory is written or cleared", () => {
    const stored = { transport: { type: "stdio", command: "npx", cwd: "/old", extra: 1 } };
    const form = {
      type: "stdio" as const,
      url: "",
      command: "npx",
      args: ["-y", "x"],
      rows: [row(), { key: "LOG_LEVEL", value: "debug", isSecret: false }],
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
