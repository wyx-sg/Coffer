// frontend/src/components/mcp/editMcpServerSave.test.ts
//
// The save path's two dealings with credential refs: which address a secret is
// written to, and which no-longer-cited addresses may be deleted afterwards.
// Both used to read `resource.name` — refs were built as `<name>.<key>` and the
// cleanup owned whatever started with `<name>.` — so the tests here rename the
// server out from under its own refs, which is the state that became reachable
// when rename became a field on `PATCH /resources/{uid}` for every kind.
import { beforeEach, describe, expect, test, vi } from "vitest";

import { getApiClient } from "@/lib/api/client";
import { mockApiClient, type ApiClientMock } from "@/test/mockApiClient";
import { saveMcpServerEdit } from "./editMcpServerSave";
import type { CredRow } from "./CredentialRowEditor";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));

const t = ((key: string) => key) as never;

/** A ref as `lib/credentialRef.ts` mints one. */
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
        credential_refs: { GITHUB_TOKEN: MINTED },
      },
    },
    ...overrides,
  } as never;
}

function row(over: Partial<CredRow> = {}): CredRow {
  return {
    id: 1,
    name: "GITHUB_TOKEN",
    value: "",
    originalRef: MINTED,
    originalName: "GITHUB_TOKEN",
    ...over,
  };
}

async function save(creds: CredRow[], res = resource()) {
  return saveMcpServerEdit({
    resource: res,
    description: "",
    configText: JSON.stringify({ transport: { type: "stdio", command: "npx", args: [] } }),
    creds,
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
    await save([row({ value: "ghp_new" })]);

    expect(api.POST).toHaveBeenCalledWith("/credentials", {
      body: { ref: MINTED, value: "ghp_new" },
    });
    expect(api.DELETE).not.toHaveBeenCalled();
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED });
  });

  test("a brand-new row gets an opaque ref, not one built from the server's name", async () => {
    await save([
      row(),
      { id: 2, name: "EXTRA", value: "s3cret", originalRef: null, originalName: null },
    ]);

    const written = (api.POST.mock.calls[0][1] as { body: { ref: string } }).body.ref;
    expect(written).toMatch(/^mcp_server\/[0-9a-f]{32}\/EXTRA$/);
    expect(written).not.toContain("github");
    expect(patchedRefs()).toEqual({ GITHUB_TOKEN: MINTED, EXTRA: written });
  });

  test("renaming the env key with a new value mints a new ref and releases the old", async () => {
    await save([row({ name: "GH_TOKEN", value: "ghp_new" })]);

    const written = (api.POST.mock.calls[0][1] as { body: { ref: string } }).body.ref;
    expect(written).toMatch(/^mcp_server\/[0-9a-f]{32}\/GH_TOKEN$/);
    expect(patchedRefs()).toEqual({ GH_TOKEN: written });
    // The address the config left behind is one Coffer minted for this server,
    // so it goes — even though the server's name no longer resembles it.
    expect(api.DELETE).toHaveBeenCalledWith("/credentials/{ref}", {
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

    expect(api.DELETE).toHaveBeenCalledWith("/credentials/{ref}", {
      params: { path: { ref: MINTED } },
    });
  });

  test("a hand-written or shared ref is never deleted", async () => {
    const shared = resource({
      config: { transport: { type: "stdio", credential_refs: { GITHUB_TOKEN: HAND_WRITTEN } } },
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
  await expect(save([row({ name: "GH_TOKEN" })])).rejects.toThrow("mcp.edit.errRenameNeedsValue");
  expect(api.PATCH).not.toHaveBeenCalled();
});

function patchedRefs(): Record<string, string> {
  const body = api.PATCH.mock.calls[0][1] as {
    body: { config: { transport: { credential_refs: Record<string, string> } } };
  };
  return body.body.config.transport.credential_refs;
}
