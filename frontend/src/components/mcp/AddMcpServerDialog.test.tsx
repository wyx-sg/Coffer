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

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: vi.fn(),
}));
vi.mock("@/lib/api/agents", () => ({
  agentsApi: { list: vi.fn(), mcpEntries: vi.fn(), adoptMcpEntry: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { put: vi.fn(), get: vi.fn() } }));

const { getApiClient } = await import("@/lib/api/client");
const { agentsApi } = await import("@/lib/api/agents");

type Call = [string, { body?: Record<string, unknown>; params?: unknown }?];
let calls: Call[];
let existing: string[];
let getOverride: ((path: string) => unknown) | null;
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
  const GET = vi.fn((path: string) =>
    Promise.resolve(
      getOverride?.(path) ?? {
        data:
          path === "/secrets"
            ? { refs: [] }
            : { resources: existing.map((name) => ({ uid: `x-${name}`, name })) },
      },
    ),
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
  getOverride = null;
  installClient();
  vi.mocked(agentsApi.list).mockResolvedValue({ items: [CLAUDE] } as never);
  vi.mocked(agentsApi.mcpEntries).mockResolvedValue({ items: [], parse_errors: [] } as never);
});

describe("AddMcpServerDialog — paste box", () => {
  acceptance("web-ui", "pasting JSON with three servers opens the review", async () => {
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
    // No Secret switch: the value is the shared row, a new secret from its 🔑 menu.
    expect(screen.queryByRole("switch")).toBeNull();
    expect(
      screen.getByRole("button", { name: "NOTION_TOKEN: secret NOTION_TOKEN" }),
    ).toBeInTheDocument();
    expect(screen.getByText("New · saved on Add")).toBeInTheDocument();
    expect(screen.getByTestId("add-server-reach")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add 3 servers" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const order = calls
      .filter((c) => c[0] === "/resources" || c[0] === "/secrets")
      .map((c) => (c[0] === "/resources" ? `register ${c[1]?.body?.name}` : "secret"));
    expect(order).toEqual(["secret", "register notion", "register figma", "register docs-search"]);
    await waitFor(() => expect(posts("/resources/mcp_server/{uid}/test")).toHaveLength(3));
  });

  acceptance("web-ui", "pasting a command line prefills a stdio server", async () => {
    renderDialog();
    paste(
      "claude mcp add github -e GITHUB_TOKEN=ghp_x -- npx -y @modelcontextprotocol/server-github",
    );
    expect(await screen.findByText("Looks like a command · stdio")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(value("Name")).toBe("github");
    expect(value("Command")).toBe("npx");
    expect(value("Arguments")).toBe("-y @modelcontextprotocol/server-github");
    // The token looks like a secret: it becomes a new one, labelled with its key.
    expect(
      screen.getByRole("button", { name: "GITHUB_TOKEN: secret GITHUB_TOKEN" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    await waitFor(() => expect(screen.getByTestId("detail-page")).toHaveTextContent(/^github$/));
    const register = posts("/resources")[0][1]?.body as {
      config: { transport: Record<string, unknown> };
    };
    expect(register.config.transport.args).toEqual(["-y", "@modelcontextprotocol/server-github"]);
    expect(calls.map((c) => c[0]).slice(0, 2)).toEqual(["/secrets", "/resources"]);
    expect(posts("/secrets")[0][1]?.body).toEqual({
      ref: expect.stringMatching(/^secret\/[0-9a-f]{32}$/),
      value: "ghp_x",
    });
    expect(register.config.transport.secret_refs).toEqual({
      GITHUB_TOKEN: expect.stringMatching(/^secret\/[0-9a-f]{32}$/),
    });
    await waitFor(() => expect(posts("/resources/mcp_server/{uid}/test")).toHaveLength(1));
  });

  acceptance("web-ui", "pasting a URL prefills a Streamable HTTP server", async () => {
    renderDialog();
    paste("https://mcp.example.com/mcp");
    expect(await screen.findByText("Looks like a URL · Streamable HTTP")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(value("URL")).toBe("https://mcp.example.com/mcp");
    expect(value("Name")).toBe("example");
    expect(screen.getByText("URL (Streamable HTTP)")).toBeInTheDocument();
  });

  acceptance("web-ui", "pasting Codex TOML reads its server tables", async () => {
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
    expect(
      screen.getByRole("button", { name: "DOCS_TOKEN: secret DOCS_TOKEN" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Value of REGION")).toHaveValue("eu");
  });

  acceptance("web-ui", "unreadable input offers a manual type choice", async () => {
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

  // The page half (one Add server action, no paste-JSON action) is
  // ResourcesPage.test.tsx.
  acceptance("web-ui", "the add dialog links to importing from agents", async () => {
    renderDialog();
    expect(
      await screen.findByRole("button", { name: /^import from your agents/i }),
    ).toBeInTheDocument();
    // MCP servers only: no custom tool, neither an OpenAPI import nor a
    // hand-made HTTP request.
    expect(document.body.textContent).not.toMatch(/custom tool|OpenAPI|HTTP request/i);
  });

  acceptance("web-ui", "the import review shows each file's diff before it imports", async () => {
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
    const entry = { agent_uid: "a-claude", name: "jira", source: "claude_json" };
    const plan = {
      servers: [
        {
          op: "add",
          name: "jira",
          original_name: null,
          name_usable: true,
          resource_uid: null,
          transport: "stdio",
          reach_agent_uids: ["a-claude"],
          reaches_all: false,
          merged: false,
          settings_differ: false,
          entries: [{ ...entry, agent_name: "claude-code", role: "source" }],
        },
      ],
      files: [
        {
          agent_uid: "a-claude",
          agent_type: "claude_code",
          source: "claude_json",
          op: "modify",
          path: "/h/.claude.json",
          display_path: "~/.claude.json",
          entries_removed: ["jira"],
          added_lines: 0,
          removed_lines: 1,
          hunks: [
            {
              header: "@@ -1,3 +1,2 @@ mcpServers",
              lines: [{ kind: "remove", old_line: 2, new_line: null, text: '"jira": {…}' }],
            },
          ],
        },
      ],
      agents: [
        {
          uid: "a-claude",
          name: "claude-code",
          display_name: "Claude Code",
          type: "claude_code",
          connected: true,
          entries_removed: ["jira"],
        },
      ],
      unavailable: [],
      changes: [],
      coffer_entry_changes: [],
    };
    postOverride = (path) => {
      if (path === "/agents/mcp-import/plan") return { data: plan, error: undefined };
      if (path === "/agents/mcp-import/apply")
        return {
          data: {
            entries: [{ ...entry, outcome: "added", server_name: "jira", resource_uid: "u-jira" }],
            servers_added: [{ name: "jira", uid: "u-jira" }],
            coffer_entry_results: [],
          },
          error: undefined,
        };
      return undefined;
    };
    renderDialog();
    const link = await screen.findByRole("button", { name: "Import from your agents · 1 found" });
    expect(document.body.textContent).not.toMatch(/custom tool|OpenAPI|HTTP request/i);

    fireEvent.click(link);
    expect(screen.getByText("Review import")).toBeInTheDocument();
    // The plan is read before anything is written: the file's diff is shown.
    expect((await screen.findAllByText("~/.claude.json")).length).toBeGreaterThan(0);
    fireEvent.click(await screen.findByRole("button", { name: "Import 1 server" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const applied = calls.find(([path]) => path === "/agents/mcp-import/apply");
    expect(applied?.[1]?.body).toEqual({ entries: [entry] });
    expect(agentsApi.adoptMcpEntry).not.toHaveBeenCalled();
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
    expect(
      screen.getByRole("button", { name: "Authorization: secret Authorization" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add server" }));
    await waitFor(() => expect(screen.getByTestId("detail-page")).toHaveTextContent("api"));

    type Http = { headers: unknown; secret_refs: Record<string, string> };
    const transport = (posts("/resources")[0][1]?.body as { config: { transport: Http } }).config
      .transport;
    expect(transport.headers).toEqual({ "X-Region": "us-east" });
    expect(transport.secret_refs).toEqual({
      Authorization: expect.stringMatching(/^secret\/[0-9a-f]{32}$/),
    });
    expect(posts("/secrets")[0][1]?.body).toEqual({
      ref: expect.stringMatching(/^secret\/[0-9a-f]{32}$/),
      value: "Bearer abc",
    });
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
    // What the paste flagged secret is stored in Coffer, not left as plain text.
    await waitFor(() => expect(posts("/secrets")).toHaveLength(1));
    expect(posts("/secrets")[0][1]?.body).toEqual({
      ref: expect.stringMatching(/^secret\/[0-9a-f]{32}$/),
      value: "Bearer t0k",
    });
  });

  acceptance(
    "web-ui",
    "a server citing an existing secret says it waits for approval before the dialog lets go",
    async () => {
      getOverride = (path) =>
        path === "/secrets/approvals"
          ? {
              data: {
                approvals: [
                  {
                    id: "ap-1",
                    op: "bind",
                    status: "pending",
                    destination_uid: "u-github",
                    ref: "secret/github-token",
                  },
                ],
              },
            }
          : undefined;
      renderDialog();
      paste("GITHUB_TOKEN=ghp_x npx -y @modelcontextprotocol/server-github");
      await continueWhenRead();
      fireEvent.click(screen.getByRole("button", { name: "Add server" }));
      expect(await screen.findByText("GITHUB_TOKEN needs approval")).toBeInTheDocument();
      expect(
        screen.getByText(/github is added\. Its secret goes to a new place/),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Open approvals" })).toBeInTheDocument();
      // Done is the only way on.
      expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Done" }));
      await waitFor(() => expect(screen.getByTestId("detail-page")).toHaveTextContent("github"));
    },
  );
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
  expect(screen.getByText(/^Names are fixed once added\./)).toBeInTheDocument();

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

acceptance("web-ui", "the add form tests the unsaved server before Add server", async () => {
  postOverride = (path) =>
    path === "/resources/mcp_server/test-config"
      ? {
          data: {
            ok: true,
            latency_ms: 1400,
            tool_count: 2,
            resource_count: 0,
            prompt_count: 0,
            tools: [
              { name: "get_issue", description: null },
              { name: "list_issues", description: null },
            ],
            stderr_tail: ["ready"],
          },
          error: undefined,
        }
      : undefined;
  renderDialog();
  paste("GITHUB_TOKEN=ghp_x npx -y @modelcontextprotocol/server-github");
  await continueWhenRead();
  fireEvent.click(screen.getByRole("button", { name: "Test" }));
  expect(await screen.findByTestId("add-test-result")).toHaveTextContent("Test passed in 1.4 s");
  expect(screen.getByText("list_issues")).toBeInTheDocument();
  const tested = calls.find(([path]) => path === "/resources/mcp_server/test-config");
  expect(tested?.[1]?.body).toMatchObject({
    transport: { type: "stdio", command: "npx", env: {}, secret_refs: {} },
    secret_values: { GITHUB_TOKEN: "ghp_x" },
  });
  // Testing saved nothing: no registration and no secret written.
  expect(calls.some(([path]) => path === "/resources" || path === "/secrets")).toBe(false);
  expect(screen.getByRole("button", { name: "Test again" })).toBeInTheDocument();
});

describe("AddMcpServerDialog — footers and failures", () => {
  test("the form has Test, Cancel and Add server, no Back; Change goes back to the paste box", async () => {
    renderDialog();
    paste("npx -y @modelcontextprotocol/server-github");
    await continueWhenRead();
    expect(screen.getByRole("button", { name: "Test" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add server" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(screen.getByLabelText("Paste a config, a command or a URL")).toHaveValue(
      "npx -y @modelcontextprotocol/server-github",
    );
  });

  test("a server that needs a variable offers to add it under Environment", async () => {
    postOverride = (path) =>
      path === "/resources/mcp_server/test-config"
        ? {
            data: {
              ok: false,
              latency_ms: 1800,
              error_code: "exited",
              exit_code: 1,
              tool_count: 0,
              stderr_tail: ["Error: GITLAB_PERSONAL_ACCESS_TOKEN is required"],
            },
            error: undefined,
          }
        : undefined;
    renderDialog();
    paste("npx -y @modelcontextprotocol/server-gitlab");
    await continueWhenRead();
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    const block = await screen.findByTestId("add-test-result");
    expect(block).toHaveTextContent("Test failed after 1.8 s · the process exited with code 1");
    expect(block).toHaveTextContent(
      "It needs GITLAB_PERSONAL_ACCESS_TOKEN. Add it under Environment, then test again.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Add the variable" }));
    const keys = screen.getAllByLabelText("Environment name") as HTMLInputElement[];
    expect(keys[keys.length - 1].value).toBe("GITLAB_PERSONAL_ACCESS_TOKEN");
  });

  acceptance("web-ui", "a batch that only partly went in stays on the review", async () => {
    postOverride = (path, init) =>
      path === "/resources" && init?.body?.name === "docs-search"
        ? {
            data: undefined,
            error: { error: { code: "RESOURCE_ALREADY_EXISTS", message: "exists" } },
            response: new Response(null, { status: 409 }),
          }
        : undefined;
    renderDialog();
    paste(
      JSON.stringify({
        mcpServers: {
          notion: { command: "npx", args: ["notion-mcp"] },
          figma: { url: "https://mcp.figma.com/mcp" },
          "docs-search": { command: "uvx", args: ["docs-search-mcp"] },
        },
      }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Review 3 servers" }));
    fireEvent.click(screen.getByRole("button", { name: "Add 3 servers" }));

    // Still open: what went in says Added, the refused one says why, and the
    // button offers only that one.
    expect(await screen.findByText("2 of 3 added")).toBeInTheDocument();
    expect(
      screen.getByText("notion and figma are added. Rename docs-search to add it too."),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Added")).toHaveLength(2);
    expect(screen.getAllByText("testing in the background")).toHaveLength(2);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Close" })).toHaveLength(2);
    const retry = screen.getByRole("button", { name: "Add 1 server" });

    postOverride = null;
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "docs" } });
    fireEvent.click(retry);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(posts("/resources").map((c) => c[1]?.body?.name)).toEqual([
      "notion",
      "figma",
      "docs-search",
      "docs",
    ]);
  });
});
