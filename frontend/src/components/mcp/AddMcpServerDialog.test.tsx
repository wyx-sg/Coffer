// frontend/src/components/mcp/AddMcpServerDialog.test.tsx
//
// The Add server dialog end to end at the component level: paste → form or
// review → the requests it sends, in order. Only the network boundary is
// mocked (the generated client, the agents and scope request modules).
import { useState } from "react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { AddMcpServerDialog } from "./AddMcpServerDialog";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
vi.mock("@/lib/api/agents", () => ({
  agentsApi: { list: vi.fn(), mcpEntries: vi.fn(), adoptMcpEntry: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { put: vi.fn(), get: vi.fn() } }));

const { getApiClient } = await import("@/lib/api/client");
const { agentsApi } = await import("@/lib/api/agents");

type Call = [string, { body?: Record<string, unknown>; params?: unknown }?];
let calls: Call[];
let existing: string[];
let postOverride: ((path: string, init: Call[1]) => unknown) | null;

const CLAUDE = { uid: "a-claude", name: "claude-code", type: "claude_code", state: "installed" };

function installClient() {
  const POST = vi.fn((path: string, init?: Call[1]) => {
    calls.push([path, init]);
    const over = postOverride?.(path, init);
    if (over !== undefined) return Promise.resolve(over);
    if (path === "/resources") {
      const name = init?.body?.name as string;
      return Promise.resolve({ data: { uid: `u-${name}`, name }, error: undefined });
    }
    if (path === "/resources/mcp_server/{uid}/test") {
      return Promise.resolve({ data: { ok: true, latency_ms: 12 }, error: undefined });
    }
    return Promise.resolve({ data: {}, error: undefined });
  });
  const GET = vi.fn(() =>
    Promise.resolve({ data: { resources: existing.map((name) => ({ uid: `x-${name}`, name })) } }),
  );
  vi.mocked(getApiClient).mockReturnValue({
    GET,
    POST,
    DELETE: vi.fn().mockResolvedValue({ data: undefined, error: undefined }),
  } as unknown as ReturnType<typeof getApiClient>);
  return POST;
}

function DetailProbe() {
  const { name } = useParams<{ name: string }>();
  return <div data-testid="detail-page">{name}</div>;
}

function Harness({ start = true }: { start?: boolean }) {
  const [open, setOpen] = useState(start);
  const [mode, setMode] = useState<"paste" | "importAgents">("paste");
  return (
    <>
      <button onClick={() => (setMode("importAgents"), setOpen(true))}>open on import</button>
      <AddMcpServerDialog open={open} onOpenChange={setOpen} initialMode={mode} />
    </>
  );
}

function renderDialog(start = true) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/mcp-servers"]}>
        <Routes>
          <Route path="/mcp-servers" element={<Harness start={start} />} />
          <Route path="/mcp-servers/:name" element={<DetailProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function paste(text: string) {
  fireEvent.change(screen.getByLabelText("Paste a config, a command or a URL"), {
    target: { value: text },
  });
}

/** Continue, once the debounced parse has recognised the paste. */
async function continueWhenRead() {
  const button = screen.getByRole("button", { name: "Continue" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

const posts = (path: string) => calls.filter((c) => c[0] === path);
const value = (label: string) => (screen.getByLabelText(label) as HTMLInputElement).value;

beforeEach(() => {
  vi.clearAllMocks();
  calls = [];
  existing = [];
  postOverride = null;
  installClient();
  vi.mocked(agentsApi.list).mockResolvedValue({ items: [CLAUDE] } as never);
  vi.mocked(agentsApi.mcpEntries).mockResolvedValue({ items: [], parse_errors: [] } as never);
});

describe("AddMcpServerDialog — paste box", () => {
  // revise-web-ui-ia: web-ui "pasting JSON with three servers opens the review" — the acceptance marker is added when the change is archived.
  test("three pasted servers open the review; adding registers each before its secrets", async () => {
    renderDialog();
    paste(
      JSON.stringify({
        mcpServers: {
          notion: {
            command: "npx",
            args: ["-y", "@notionhq/notion-mcp-server"],
            env: { NOTION_TOKEN: "secret_n" },
          },
          figma: { url: "https://mcp.figma.com/mcp" },
          "docs-search": { command: "uvx", args: ["docs-search-mcp"] },
        },
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Review 3 servers" }));
    expect(screen.getByText("Review before adding")).toBeInTheDocument();
    expect(screen.getByText("3 servers found")).toBeInTheDocument();
    expect(screen.getByText(/NOTION_TOKEN looks like a secret/)).toBeInTheDocument();
    expect(screen.getByTestId("add-server-reach")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add 3 servers" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const order = calls
      .filter((c) => c[0] === "/resources" || c[0] === "/secrets")
      .map((c) => (c[0] === "/resources" ? `register ${c[1]?.body?.name}` : "secret"));
    expect(order).toEqual(["register notion", "secret", "register figma", "register docs-search"]);
    await waitFor(() => expect(posts("/resources/mcp_server/{uid}/test")).toHaveLength(3));
  });

  // revise-web-ui-ia: web-ui "pasting a command line prefills a stdio server" — the acceptance marker is added when the change is archived.
  test("a claude mcp add line prefills the stdio form, and Add opens the server's page", async () => {
    renderDialog();
    paste(
      "claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github",
    );
    expect(await screen.findByText("Looks like a command · stdio")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(value("Name")).toBe("github");
    expect(value("Command")).toBe("npx");
    expect(value("Arguments")).toBe("-y @modelcontextprotocol/server-github");
    expect(screen.getByRole("switch", { name: "GITHUB_TOKEN is a secret" })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    await waitFor(() => expect(screen.getByTestId("detail-page")).toHaveTextContent(/^github$/));
    const register = posts("/resources")[0][1]?.body as {
      config: { transport: Record<string, unknown> };
    };
    expect(register.config.transport.args).toEqual(["-y", "@modelcontextprotocol/server-github"]);
    expect(calls.map((c) => c[0]).slice(0, 2)).toEqual(["/resources", "/secrets"]);
    await waitFor(() => expect(posts("/resources/mcp_server/{uid}/test")).toHaveLength(1));
  });

  // revise-web-ui-ia: web-ui "pasting a URL prefills a Streamable HTTP server" — the acceptance marker is added when the change is archived.
  test("a URL prefills the HTTP form with a name from the host", async () => {
    renderDialog();
    paste("https://mcp.example.com/mcp");
    expect(await screen.findByText("Looks like a URL · Streamable HTTP")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(value("URL")).toBe("https://mcp.example.com/mcp");
    expect(value("Name")).toBe("example");
    expect(screen.getByText("URL (Streamable HTTP)")).toBeInTheDocument();
  });

  // revise-web-ui-ia: web-ui "pasting Codex TOML reads its server tables" — the acceptance marker is added when the change is archived.
  test("a Codex [mcp_servers.docs] table prefills the stdio form", async () => {
    renderDialog();
    paste(
      [
        "[mcp_servers.docs]",
        'command = "uvx"',
        'args = ["docs-mcp", "--verbose"]',
        "[mcp_servers.docs.env]",
        'DOCS_TOKEN = "abc"',
        'REGION = "eu"',
      ].join("\n"),
    );
    await continueWhenRead();
    expect(value("Name")).toBe("docs");
    expect(value("Command")).toBe("uvx");
    expect(value("Arguments")).toBe("docs-mcp --verbose");
    expect(screen.getByRole("switch", { name: "DOCS_TOKEN is a secret" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "REGION is a secret" })).not.toBeChecked();
  });

  // revise-web-ui-ia: web-ui "unreadable input offers a manual type choice" — the acceptance marker is added when the change is archived.
  test("unreadable input says so and offers stdio / HTTP, sending nothing", async () => {
    renderDialog();
    paste("Install the server first, then restart your editor.");
    expect(await screen.findByText("Couldn't read this — choose a type below")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Command \(stdio\)/ }));
    expect(value("Command")).toBe("");
    expect(value("Name")).toBe("");
    expect(calls).toEqual([]);
  });

  // Base scenario web-ui "JSON import shows readable error for malformed JSON" (marker on the e2e spec).
  test("malformed JSON shows where it broke, never a generic error, and sends nothing", async () => {
    renderDialog();
    paste('{\n  "mcpServers": {\n    "fs": { command: "npx" }\n  }\n}');
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/line 3, column/);
    expect(document.body.textContent).not.toMatch(/unexpected error|INTERNAL_ERROR/i);
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    expect(calls).toEqual([]);
  });

  // revise-web-ui-ia: web-ui "the add dialog links to importing from agents" — the acceptance marker is added when the change is archived.
  test("the dialog links to importing from agents and offers no custom tool", async () => {
    vi.mocked(agentsApi.mcpEntries).mockResolvedValue({
      items: [
        {
          name: "jira",
          source: "claude_json",
          transport: "stdio",
          command: "npx",
          args: ["-y", "mcp-atlassian"],
          env_keys: ["JIRA_TOKEN"],
          secret_keys: ["JIRA_TOKEN"],
          header_keys: [],
          url: null,
          enabled: null,
          is_coffer: false,
          matches_resource: null,
        },
      ],
      parse_errors: [],
    } as never);
    vi.mocked(agentsApi.adoptMcpEntry).mockResolvedValue({
      uid: "u-jira",
      kind: "mcp_server",
      name: "jira",
    } as never);
    renderDialog();
    const link = await screen.findByRole("button", { name: "Import from your agents · 1 found" });
    expect(document.body.textContent).not.toMatch(/custom tool|OpenAPI|HTTP request/i);

    fireEvent.click(link);
    expect(screen.getByText("Review import")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import 1 server" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(agentsApi.adoptMcpEntry).toHaveBeenCalledWith("a-claude", "jira", {
      source: "claude_json",
      secrets: { JIRA_TOKEN: "mcp/claude-code/jira/JIRA_TOKEN" },
    });
  });
});

describe("AddMcpServerDialog — form", () => {
  test("a name another server has is said before submit, and on the daemon's 409", async () => {
    existing = ["github"];
    renderDialog();
    paste("npx -y @modelcontextprotocol/server-github");
    await continueWhenRead();
    expect(
      await screen.findByText("A server called github already exists. Pick another name."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add server" })).toBeDisabled();

    // Taken meanwhile (the list did not know yet): the 409 lands on the field.
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "gh" } });
    postOverride = (path) =>
      path === "/resources"
        ? {
            data: undefined,
            error: { error: { code: "RESOURCE_ALREADY_EXISTS", message: "exists" } },
          }
        : undefined;
    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    expect(
      await screen.findByText("A server called gh already exists. Pick another name."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  test("a header secret goes to the keychain and the config keeps only its ref", async () => {
    renderDialog();
    paste(
      JSON.stringify({
        mcpServers: {
          api: {
            url: "https://example.com/mcp",
            headers: { Authorization: "Bearer abc", "X-Region": "us-east" },
          },
        },
      }),
    );
    await continueWhenRead();
    expect(screen.getByRole("switch", { name: "Authorization is a secret" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    await waitFor(() => expect(screen.getByTestId("detail-page")).toHaveTextContent("api"));

    type Http = { headers: unknown; secret_refs: Record<string, string> };
    const transport = (posts("/resources")[0][1]?.body as { config: { transport: Http } }).config
      .transport;
    expect(transport.headers).toEqual({ "X-Region": "us-east" });
    const ref = transport.secret_refs.Authorization;
    expect(ref).toMatch(/^mcp_server\/[0-9a-f]{32}\/Authorization$/);
    expect(posts("/secrets")[0][1]?.body).toEqual({ ref, value: "Bearer abc" });
  });

  test("a bearer_token_env_var header asks for its value and sends no empty secret", async () => {
    renderDialog();
    paste(
      [
        "[mcp_servers.api]",
        'url = "https://example.com/mcp"',
        'bearer_token_env_var = "API_TOKEN"',
      ].join("\n"),
    );
    await continueWhenRead();
    expect(screen.getByText(/Enter the value of Authorization/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add server" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Value of Authorization"), {
      target: { value: "Bearer t0k" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    await waitFor(() => expect(posts("/secrets")).toHaveLength(1));
    expect(posts("/secrets")[0][1]?.body?.value).toBe("Bearer t0k");
  });

  test("a secret held for approval (202) is said before the dialog lets go", async () => {
    postOverride = (path) =>
      path === "/secrets"
        ? { data: { approval: { id: "ap-1" } }, error: undefined }
        : undefined;
    renderDialog();
    paste("GITHUB_TOKEN=ghp_x npx -y @modelcontextprotocol/server-github");
    await continueWhenRead();
    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    expect(await screen.findByText("Waiting for approval")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open approvals" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.getByTestId("detail-page")).toHaveTextContent("github"));
  });
});

acceptance("web-ui", "the import review shows each server's fixed name", async () => {
  const LONG = "a-very-long-server-name-thirty"; // 30 characters
  expect(LONG.length).toBe(30);
  renderDialog();
  paste(
    JSON.stringify({
      mcpServers: {
        "My Server": { command: "npx" },
        "github-tools": { command: "npx" },
        [LONG]: { command: "npx" },
      },
    }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Review 3 servers" }));

  // Each name is shown as the one it keeps, with the note that it is fixed.
  const names = screen.getAllByLabelText("Name") as HTMLInputElement[];
  expect(names.map((n) => n.value)).toEqual(["my-server", "github-tools", LONG]);
  expect(screen.getByText("Renamed from My Server.")).toBeInTheDocument();
  expect(screen.getAllByText("Can't be changed once added.")).toHaveLength(2);

  // Only the 30-character name is flagged, naming the limit, and nothing is sent.
  const flag = screen.getByRole("alert");
  expect(flag).toHaveTextContent("30 characters; names are at most 24");
  const add = screen.getByRole("button", { name: "Add 3 servers" });
  expect(add).toBeDisabled();
  fireEvent.click(add);
  expect(posts("/resources")).toHaveLength(0);

  // Shortened in the review, it can be added.
  fireEvent.change(names[2], { target: { value: "long-server" } });
  expect(within(screen.getByRole("dialog")).queryByRole("alert")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Add 3 servers" }));
  await waitFor(() => expect(posts("/resources")).toHaveLength(3));
  expect(posts("/resources").map((c) => c[1]?.body?.name)).toEqual([
    "my-server",
    "github-tools",
    "long-server",
  ]);
});

test("opened by the page on Import from your agents, it starts on that view", async () => {
  renderDialog(false);
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "open on import" }));
  expect(await screen.findByText("Review import")).toBeInTheDocument();
});
