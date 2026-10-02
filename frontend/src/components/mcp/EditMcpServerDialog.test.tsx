// frontend/src/components/mcp/EditMcpServerDialog.test.tsx
// The edit dialog: fields over the stored config, the Secret | Plain rows with
// the stored-secret picker, Replace, and Test on the unsaved form.
import { useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EditMcpServerDialog } from "./EditMcpServerDialog";
import type { components } from "@/lib/api/types";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
// Only the stored-secret list is faked; set/remove stay real so the save path's
// writes reach the mocked client.
vi.mock("@/lib/api/secret", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/secret")>();
  return { ...actual, secretsApi: { ...actual.secretsApi, list: vi.fn() } };
});

const { getApiClient } = await import("@/lib/api/client");
const { secretsApi } = await import("@/lib/api/secret");
const getApiClientMock = vi.mocked(getApiClient);

type ResourceOut = components["schemas"]["ResourceOut"];

const OWN = "gh.GITHUB_TOKEN";

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
      secret_refs: { GITHUB_TOKEN: OWN },
    },
  },
  enabled: true,
  toggleable: true,
  secrets_readable_by_local_processes: false,
  created_at: "2026-05-21T00:00:00Z",
  updated_at: "2026-05-21T00:00:00Z",
};

const httpResource: ResourceOut = {
  ...stdioResource,
  uid: "u-docs",
  name: "docs",
  config: { transport: { type: "http", url: "https://a.example/mcp", headers: { "X-R": "eu" } } },
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

function openDialog(resource: ResourceOut = stdioResource, focus?: "secret") {
  render(wrap(<Harness resource={resource} focus={focus} />));
  fireEvent.click(screen.getByRole("button", { name: "edit" }));
}

function client() {
  const order: string[] = [];
  const api = {
    PATCH: vi.fn().mockImplementation((p: string) => {
      order.push(`PATCH:${p}`);
      return Promise.resolve({ data: {}, error: undefined });
    }),
    POST: vi.fn().mockImplementation((p: string) => {
      order.push(`POST:${p}`);
      return Promise.resolve({ data: {}, error: undefined });
    }),
    DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
    order,
  };
  getApiClientMock.mockReturnValue(api as unknown as ReturnType<typeof getApiClient>);
  return api;
}

const patchBody = (patch: ReturnType<typeof vi.fn>) =>
  patch.mock.calls[0][1].body as {
    title?: string | null;
    description?: string | null;
    config: { transport: Record<string, unknown> } & Record<string, unknown>;
  };

type Api = ReturnType<typeof client>;
const TEST_PATH = "/resources/mcp_server/test-config";

/** Answer the test-config POST with `data`; every other POST as the client does. */
function testResult(api: Api, data: Record<string, unknown>) {
  const base = api.POST.getMockImplementation();
  api.POST.mockImplementation((p: string, ...rest: unknown[]) =>
    p === TEST_PATH ? Promise.resolve({ data, error: undefined }) : base?.(p, ...rest),
  );
}

const testCall = (api: Api) => api.POST.mock.calls.find((c) => c[0] === TEST_PATH);

const save = () => fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(secretsApi.list).mockResolvedValue({
    refs: [
      { ref: OWN, present: true },
      { ref: "secret/GITHUB_PAT", present: true },
    ],
  } as never);
});

describe("EditMcpServerDialog", () => {
  test("shows the fixed name, the description and the transport as fields", async () => {
    client();
    openDialog();
    expect(screen.getByText("Edit gh")).toBeInTheDocument();
    expect(screen.getByText("Changes apply to new agent sessions.")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toHaveValue("GitHub MCP");
    expect(screen.getByLabelText("Command")).toHaveValue("npx");
    expect(screen.getByLabelText("Arguments")).toHaveValue(
      "-y @modelcontextprotocol/server-github",
    );
    expect(screen.getByLabelText("Working directory")).toHaveValue("/tmp/gh");
    // A stored secret shows its key, Secret pressed, "Stored" — never a value.
    const keys = screen.getAllByLabelText("Environment name");
    expect(keys.map((k) => (k as HTMLInputElement).value)).toEqual(["GITHUB_TOKEN", "LOG_LEVEL"]);
    const kind = screen.getByRole("group", { name: "How GITHUB_TOKEN is kept" });
    expect(within(kind).getByRole("button", { name: "Secret" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await screen.findByText("Stored")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace" })).toBeInTheDocument();
    expect(screen.getByLabelText("Start timeout")).toHaveValue(30);
  });

  test("saves the fields over the stored config, keeping every key the form does not show", async () => {
    const api = client();
    openDialog();
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Repos" } });
    fireEvent.change(screen.getByLabelText("Arguments"), { target: { value: "-y 'a b'" } });
    fireEvent.change(screen.getByLabelText("Working directory"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Request timeout"), { target: { value: "45" } });
    save();
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    const body = patchBody(api.PATCH);
    expect(body.description).toBe("Repos");
    expect(body).not.toHaveProperty("title");
    expect(body.config.transport).toMatchObject({
      type: "stdio",
      command: "npx",
      args: ["-y", "a b"],
      env: { LOG_LEVEL: "debug" },
      secret_refs: { GITHUB_TOKEN: OWN },
    });
    expect(body.config.transport).not.toHaveProperty("cwd");
    expect(body.config.request_timeout_seconds).toBe(45);
    expect(body.config.spawn_timeout_seconds).toBe(30);
    // Kept as it was: no value was typed, so nothing is written.
    expect(api.POST).not.toHaveBeenCalled();
  });

  test("an http server edits its URL and headers, with no start timeout", async () => {
    const api = client();
    openDialog(httpResource);
    expect(screen.queryByLabelText("Start timeout")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Working directory")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://b.example/mcp" } });
    save();
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    expect(patchBody(api.PATCH).config.transport).toMatchObject({
      url: "https://b.example/mcp",
      headers: { "X-R": "eu" },
    });
  });

  test("opened for a secret, the first stored one is ready to replace", () => {
    client();
    openDialog(stdioResource, "secret");
    expect(screen.getByLabelText("New value of GITHUB_TOKEN")).toHaveFocus();
  });

  test("Replace writes the new value through the same ref, BEFORE the resource PATCH", async () => {
    const api = client();
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    const input = screen.getByLabelText("New value of GITHUB_TOKEN");
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "new-secret-token" } });
    save();
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    expect(api.order).toEqual(["POST:/secrets", "PATCH:/resources/{uid}"]);
    expect(api.POST.mock.calls[0][1].body).toEqual({ ref: OWN, value: "new-secret-token" });
    expect(api.PATCH).toHaveBeenCalledWith(
      "/resources/{uid}",
      expect.objectContaining({ params: { path: { uid: "u-github" } } }),
    );
    expect(patchBody(api.PATCH).config.transport.secret_refs).toEqual({ GITHUB_TOKEN: OWN });
  });

  test("picking a Secrets-page secret cites secret/<name> and writes no value", async () => {
    const api = client();
    openDialog();
    const trigger = await screen.findByRole("combobox", { name: "Stored secret for GITHUB_TOKEN" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "GITHUB_PAT" }));
    save();
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    expect(api.POST).not.toHaveBeenCalled();
    expect(patchBody(api.PATCH).config.transport.secret_refs).toEqual({
      GITHUB_TOKEN: "secret/GITHUB_PAT",
    });
  });

  test("switching a row to Plain moves it to env and drops its ref", async () => {
    const api = client();
    openDialog();
    const kind = screen.getByRole("group", { name: "How GITHUB_TOKEN is kept" });
    fireEvent.click(within(kind).getByRole("button", { name: "Plain" }));
    fireEvent.change(screen.getByLabelText("Value of GITHUB_TOKEN"), {
      target: { value: "public" },
    });
    save();
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    const transport = patchBody(api.PATCH).config.transport;
    expect(transport.env).toEqual({ GITHUB_TOKEN: "public", LOG_LEVEL: "debug" });
    expect(transport.secret_refs).toEqual({});
  });

  test("Add variable adds a Plain row; the trash removes one", () => {
    client();
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    expect(screen.getAllByLabelText("Environment name")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Remove GITHUB_TOKEN" }));
    expect(screen.queryByText("Stored")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Environment name")).toHaveLength(2);
  });

  test("Test runs the unsaved form with typed secrets and shows the outcome", async () => {
    const api = client();
    testResult(api, {
      ok: true,
      latency_ms: 1420,
      tool_count: 26,
      resource_count: null,
      prompt_count: 0,
    });
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    fireEvent.change(screen.getByLabelText("New value of GITHUB_TOKEN"), {
      target: { value: "typed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(
      await screen.findByText("Test passed in 1.4 s · 26 tools, 0 resources, 0 prompts"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Test again" })).toBeInTheDocument();
    const [path, opts] = testCall(api) as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/resources/mcp_server/test-config");
    expect(opts.body.secret_values).toEqual({ GITHUB_TOKEN: "typed" });
    expect(opts.body.transport).not.toHaveProperty("secret_refs");
    expect(opts.body.transport).not.toHaveProperty("secret_refs");
    expect(opts.body.transport).toMatchObject({ command: "npx", env: { LOG_LEVEL: "debug" } });
  });

  test("a failed test says why, and that nothing was saved", async () => {
    const api = client();
    testResult(api, {
      ok: false,
      latency_ms: 3000,
      error_code: "stored_secret_not_released",
      error_message: "A stored secret is released only to a server that is added and approved.",
    });
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(
      await screen.findByText("Test failed after 3.0 s · stored secret not released"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/released only to a server .* Nothing was saved\./),
    ).toBeInTheDocument();
    const [, opts] = testCall(api) as [string, { body: { transport: object } }];
    expect(opts.body.transport).toMatchObject({ secret_refs: { GITHUB_TOKEN: OWN } });
    expect(api.PATCH).not.toHaveBeenCalled();
  });
});
