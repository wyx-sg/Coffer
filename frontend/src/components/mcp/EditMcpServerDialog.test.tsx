// frontend/src/components/mcp/EditMcpServerDialog.test.tsx
import { useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditMcpServerDialog } from "./EditMcpServerDialog";
import type { components } from "@/lib/api/types";

vi.mock("@/lib/api/client", () => ({
  getApiClient: vi.fn(),
}));

const { getApiClient } = await import("@/lib/api/client");
const getApiClientMock = vi.mocked(getApiClient);

type ResourceOut = components["schemas"]["ResourceOut"];

// The uid is identity, the name is the label. They are deliberately different
// strings here: the PATCH is addressed to the uid while the credential refs the
// save mints still spell the NAME, and only distinct values can tell the two
// apart.
const stdioResource: ResourceOut = {
  uid: "u-github",
  kind: "mcp_server",
  name: "gh",
  title: null,
  scope: null,
  description: "GitHub MCP",
  config: {
    transport: {
      type: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-github"],
      env: { LOG_LEVEL: "debug" },
      cwd: "/tmp/gh",
      credential_refs: { GITHUB_TOKEN: "gh.GITHUB_TOKEN" },
    },
  },
  enabled: true,
  toggleable: true,
  secrets_readable_by_local_processes: false,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

const noCredsResource: ResourceOut = {
  uid: "u-filesystem",
  kind: "mcp_server",
  name: "fs",
  title: null,
  scope: null,
  description: "Filesystem MCP",
  config: {
    transport: { type: "stdio", command: "npx" },
  },
  enabled: true,
  toggleable: true,
  secrets_readable_by_local_processes: false,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>;
}

/** The dialog is controlled; the harness plays the detail header's Edit button. */
function Harness({ resource, focus }: { resource: ResourceOut; focus?: "secret" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>edit</button>
      <EditMcpServerDialog resource={resource} open={open} onOpenChange={setOpen} focus={focus} />
    </>
  );
}

function openDialog() {
  fireEvent.click(screen.getByRole("button", { name: "edit" }));
}

function client(over: Record<string, unknown> = {}) {
  const api = {
    PATCH: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
    POST: vi.fn().mockResolvedValue({ data: {}, error: undefined }),
    DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    ...over,
  };
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

const patchBody = (patch: ReturnType<typeof vi.fn>) =>
  patch.mock.calls[0][1].body as {
    title?: string | null;
    config: { transport: Record<string, unknown> } & Record<string, unknown>;
  };

describe("EditMcpServerDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("shows the fixed name, the title and the transport as fields", () => {
    client();
    render(wrap(<Harness resource={{ ...stdioResource, title: "GitHub" }} />));
    openDialog();
    expect(screen.getByText("Edit gh")).toBeInTheDocument();
    expect(screen.getByText("Changes apply to new agent sessions.")).toBeInTheDocument();
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("GitHub");
    expect((screen.getByLabelText("Command") as HTMLInputElement).value).toBe("npx");
    expect((screen.getByLabelText("Arguments") as HTMLInputElement).value).toBe(
      "-y @modelcontextprotocol/server-github",
    );
    // A stored secret shows its key and "Stored" — never a value.
    expect(screen.getByText("GITHUB_TOKEN")).toBeInTheDocument();
    expect(screen.getByText("Stored")).toBeInTheDocument();
  });

  test("saves the fields over the stored config, keeping every key the form does not show", async () => {
    const api = client();
    render(wrap(<Harness resource={stdioResource} />));
    openDialog();
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "GitHub" } });
    fireEvent.change(screen.getByLabelText("Arguments"), { target: { value: "-y 'a b'" } });
    fireEvent.change(screen.getByLabelText(/^request$/i), { target: { value: "45" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    const body = patchBody(api.PATCH);
    expect(body.title).toBe("GitHub");
    expect(body.config.transport).toMatchObject({
      type: "stdio",
      command: "npx",
      args: ["-y", "a b"],
      env: { LOG_LEVEL: "debug" },
      cwd: "/tmp/gh",
    });
    expect(body.config.request_timeout_seconds).toBe(45);
    expect(body.config.spawn_timeout_seconds).toBe(30);
  });

  test("an http server edits its URL and plain headers", async () => {
    const api = client();
    const http: ResourceOut = {
      ...noCredsResource,
      config: {
        transport: { type: "http", url: "https://a.example/mcp", headers: { "X-R": "eu" } },
      },
    };
    render(wrap(<Harness resource={http} />));
    openDialog();
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://b.example/mcp" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    expect(patchBody(api.PATCH).config.transport).toMatchObject({
      url: "https://b.example/mcp",
      headers: { "X-R": "eu" },
    });
  });

  test("opened for a secret, the first stored one is ready to replace", () => {
    client();
    render(wrap(<Harness resource={stdioResource} focus="secret" />));
    openDialog();
    expect(screen.getByLabelText("New value of GITHUB_TOKEN")).toHaveFocus();
  });

  test("adds and removes secret rows", () => {
    client();
    render(wrap(<Harness resource={stdioResource} />));
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /add secret/i }));
    expect(screen.getByPlaceholderText("GITHUB_TOKEN")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /remove secret/i })[0]);
    expect(screen.queryByText("Stored")).not.toBeInTheDocument();
  });

  test("keep-existing path: leaves value='' for unchanged creds, PATCH still has ref in credential_refs", async () => {
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const deleteMock = vi.fn().mockResolvedValue({ data: undefined, error: undefined });
    getApiClientMock.mockReturnValue({
      PATCH: patchMock,
      POST: postMock,
      DELETE: deleteMock,
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<Harness resource={stdioResource} />));
    openDialog();

    // Don't change the credential value — keep the placeholder ("keep existing")
    // Save immediately
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalled();
    });

    // Credential store POST should NOT be called (value is empty)
    expect(postMock).not.toHaveBeenCalledWith("/credentials", expect.anything());

    // PATCH body should still contain the original ref for GITHUB_TOKEN
    const patchArgs = patchMock.mock.calls[0];
    const body = patchArgs[1].body as {
      config: { transport: { credential_refs: Record<string, string> } };
    };
    expect(body.config.transport.credential_refs).toEqual({
      GITHUB_TOKEN: "gh.GITHUB_TOKEN",
    });
  });

  test("on save with a NEW credential value, keychain write fires BEFORE the resource PATCH", async () => {
    const callOrder: string[] = [];
    const postMock = vi.fn().mockImplementation((path: string) => {
      callOrder.push(`POST:${path}`);
      return Promise.resolve({ data: {}, error: undefined });
    });
    const patchMock = vi.fn().mockImplementation((path: string) => {
      callOrder.push(`PATCH:${path}`);
      return Promise.resolve({ data: {}, error: undefined });
    });
    getApiClientMock.mockReturnValue({
      POST: postMock,
      PATCH: patchMock,
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<Harness resource={stdioResource} />));
    openDialog();

    // Set a new value for the existing credential
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    const passwordInputs = screen.getAllByPlaceholderText(/Leave blank to keep/i);
    fireEvent.change(passwordInputs[0], { target: { value: "new-secret-token" } });

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalled();
    });

    // Credential store write must happen before resource PATCH
    const keychainIdx = callOrder.indexOf("POST:/credentials");
    const patchIdx = callOrder.findIndex((c) => c.startsWith("PATCH:"));
    expect(keychainIdx).toBeGreaterThanOrEqual(0);
    expect(patchIdx).toBeGreaterThanOrEqual(0);
    expect(keychainIdx).toBeLessThan(patchIdx);

    // Credential store payload has the correct ref and value
    const keychainCall = postMock.mock.calls.find((c) => c[0] === "/credentials");
    expect(keychainCall?.[1].body).toEqual({
      ref: "gh.GITHUB_TOKEN",
      value: "new-secret-token",
    });

    // PATCH body includes the ref
    const patchArgs = patchMock.mock.calls[0];
    const body = patchArgs[1].body as {
      config: { transport: { credential_refs: Record<string, string> } };
    };
    expect(body.config.transport.credential_refs).toEqual({
      GITHUB_TOKEN: "gh.GITHUB_TOKEN",
    });
  });

  test("PATCHes /resources/{uid} while the credential refs it mints spell the NAME", async () => {
    // The two halves of the identity split meet in this one save: the request
    // is routed by the uid (so it keeps resolving after a rename), and the ref
    // written into the credential store keeps the `<name>.` spelling every
    // already-stored ref uses — this dialog holds no plaintext to migrate them
    // with, which is also why it offers no rename.
    const patchMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    const postMock = vi.fn().mockResolvedValue({ data: {}, error: undefined });
    getApiClientMock.mockReturnValue({
      PATCH: patchMock,
      POST: postMock,
      DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    } as unknown as ReturnType<typeof getApiClient>);

    render(wrap(<Harness resource={stdioResource} />));
    openDialog();

    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    const passwordInputs = screen.getAllByPlaceholderText(/Leave blank to keep/i);
    fireEvent.change(passwordInputs[0], { target: { value: "rotated" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(patchMock).toHaveBeenCalled());

    // No kind segment: a uid already names exactly one row.
    expect(patchMock).toHaveBeenCalledWith(
      "/resources/{uid}",
      expect.objectContaining({ params: { path: { uid: "u-github" } } }),
    );
    expect(postMock.mock.calls.find((c) => c[0] === "/credentials")?.[1].body).toEqual({
      ref: "gh.GITHUB_TOKEN",
      value: "rotated",
    });
  });
});
