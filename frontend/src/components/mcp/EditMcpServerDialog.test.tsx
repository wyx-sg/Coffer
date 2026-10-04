// frontend/src/components/mcp/EditMcpServerDialog.test.tsx
// The edit dialog: fields over the stored config, the shared header / env rows
// (plain text, a stored secret, a new secret), Test on the unsaved form, and a
// failed save that stays in the dialog with Retry.
import { useState } from "react";
import { acceptance } from "@/test/acceptance";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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

/** The ref Coffer minted for this server's key, . */
const OWN = "mcp_server/gh/GITHUB_TOKEN";

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
  delivery: null,
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
function Harness({ resource }: { resource: ResourceOut }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>edit</button>
      <EditMcpServerDialog resource={resource} open={open} onOpenChange={setOpen} />
    </>
  );
}

function openDialog(resource: ResourceOut = stdioResource) {
  render(wrap(<Harness resource={resource} />));
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
      {
        ref: OWN,
        present: true,
        locked: false,
        bindings: [],
        cited_by: [],
        mentioned_by_skills: [],
      },
      {
        ref: "secret/github-pat",
        present: true,
        locked: false,
        bindings: [],
        cited_by: [],
        mentioned_by_skills: [],
      },
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
    // A chosen secret shows its name, never a value; a plain row shows its text.
    const keys = screen.getAllByLabelText("Environment name");
    expect(keys.map((k) => (k as HTMLInputElement).value)).toEqual(["GITHUB_TOKEN", "LOG_LEVEL"]);
    expect(
      screen.getByRole("button", { name: "GITHUB_TOKEN: secret GITHUB_TOKEN" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Value of LOG_LEVEL")).toHaveValue("debug");
    expect(screen.getByLabelText("Start timeout")).toHaveValue(30);
    expect(screen.getByLabelText("Request timeout")).toHaveValue(120);
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
    // The same secret is still chosen: nothing is written.
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

  test("a plain value stored in Coffer is written before the PATCH and cited by name", async () => {
    const api = client();
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    const keys = screen.getAllByLabelText("Environment name");
    fireEvent.change(keys[keys.length - 1], { target: { value: "API_TOKEN" } });
    fireEvent.change(screen.getByLabelText("Value of API_TOKEN"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Store it in Coffer?" }));
    save();
    await waitFor(() => expect(api.PATCH).toHaveBeenCalled());
    expect(api.order).toEqual(["POST:/secrets", "PATCH:/resources/{uid}"]);
    expect(api.POST.mock.calls[0][1].body).toEqual({ ref: "secret/api_token", value: "abc" });
    expect(patchBody(api.PATCH).config.transport.secret_refs).toEqual({
      GITHUB_TOKEN: OWN,
      API_TOKEN: "secret/api_token",
    });
  });

  test("Add variable adds a plain row; the trash removes one", () => {
    client();
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    expect(screen.getAllByLabelText("Environment name")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Remove GITHUB_TOKEN" }));
    expect(screen.getAllByLabelText("Environment name")).toHaveLength(2);
  });

  test("Test runs the unsaved form and shows the outcome in a neutral block", async () => {
    const api = client();
    testResult(api, {
      ok: true,
      latency_ms: 1420,
      tool_count: 26,
      resource_count: null,
      prompt_count: 0,
    });
    openDialog(httpResource);
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    const block = await screen.findByTestId("add-test-result");
    expect(block).toHaveTextContent("Test passed in 1.4 s · 26 tools, 0 resources, 0 prompts");
    expect(block).toHaveClass("bg-surface-sunken");
    expect(screen.getByRole("button", { name: "Test again" })).toBeInTheDocument();
    const [path, opts] = testCall(api) as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/resources/mcp_server/test-config");
    expect(opts.body.transport).toMatchObject({ url: "https://a.example/mcp" });
    expect(api.PATCH).not.toHaveBeenCalled();
  });

  test("a new secret travels in secret_values for the test only", async () => {
    const api = client();
    testResult(api, { ok: true, latency_ms: 100, tool_count: 1 });
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    const keys = screen.getAllByLabelText("Environment name");
    fireEvent.change(keys[keys.length - 1], { target: { value: "API_TOKEN" } });
    fireEvent.change(screen.getByLabelText("Value of API_TOKEN"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Store it in Coffer?" }));
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    await screen.findByTestId("add-test-result");
    const [, opts] = testCall(api) as [string, { body: Record<string, unknown> }];
    expect(opts.body.secret_values).toEqual({ API_TOKEN: "abc" });
    expect(opts.body.transport).toMatchObject({ secret_refs: { GITHUB_TOKEN: OWN } });
    expect(api.POST.mock.calls.some((c) => c[0] === "/secrets")).toBe(false);
  });

  test("a failed test says why and that nothing was saved", async () => {
    const api = client();
    testResult(api, {
      ok: false,
      latency_ms: 3000,
      error_code: "connect_failed",
      error_message: "mcp.example:443 isn't accepting connections.",
      stderr_tail: [],
    });
    openDialog(httpResource);
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(
      await screen.findByText("Test failed after 3.0 s · couldn't connect"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/isn't accepting connections\. Nothing was saved\./),
    ).toBeInTheDocument();
    expect(screen.getByTestId("add-test-result")).toHaveClass("bg-danger-soft");
    expect(api.PATCH).not.toHaveBeenCalled();
  });

  test("a server that needs a variable offers to add it", async () => {
    const api = client();
    testResult(api, {
      ok: false,
      latency_ms: 1800,
      error_code: "exited",
      exit_code: 1,
      tool_count: 0,
      stderr_tail: ["Error: GITLAB_PERSONAL_ACCESS_TOKEN is required"],
    });
    openDialog();
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    expect(
      await screen.findByText(/It needs GITLAB_PERSONAL_ACCESS_TOKEN\. Add it under Environment/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add the variable" }));
    const keys = screen.getAllByLabelText("Environment name") as HTMLInputElement[];
    expect(keys[keys.length - 1].value).toBe("GITLAB_PERSONAL_ACCESS_TOKEN");
  });

  acceptance(
    "web-ui",
    "a failed save stays in the Edit dialog and Save becomes Retry",
    async () => {
      const api = client();
      api.PATCH.mockResolvedValueOnce({
        data: undefined,
        error: { error: { code: "INTERNAL_ERROR", message: "The daemon didn't answer." } },
        response: new Response(null, { status: 500 }),
      });
      openDialog();
      fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Repos" } });
      save();
      expect(await screen.findByText("Couldn't save gh")).toBeInTheDocument();
      expect(screen.getByText(/Your edits are still here/)).toBeInTheDocument();
      expect(screen.getByLabelText("Description")).toHaveValue("Repos");
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      await waitFor(() => expect(api.PATCH).toHaveBeenCalledTimes(2));
    },
  );
});
