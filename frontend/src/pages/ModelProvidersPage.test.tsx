// src/pages/ModelProvidersPage.test.tsx — the Model providers list: the split, the rows, first-run, and Add.
//
// The page is one list + detail: `/model-providers` opens its first provider,
// each row says what the provider offers and who runs on it (agents by their
// mark, Coffer's own uses by their badge), and Add is a two-step dialog —
// Endpoint (tested with the unsaved key inline) then Models. The network is
// mocked at the api modules and the introspection hooks.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AgentOut } from "@/lib/api/agents";
import type { Provider, ProviderModel } from "@/lib/api/providers";
import { acceptance } from "@/test/acceptance";
import { ModelProvidersPage } from "./ModelProvidersPage";

vi.mock("@/lib/api/providers", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/providers")>()),
  providersApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    activate: vi.fn(),
    detectLocal: vi.fn(),
    health: vi.fn(),
  },
}));
vi.mock("@/components/usage/UsageTab", () => ({ UsageTab: () => <p>usage tab body</p> }));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn(), rename: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: {
    pendingApprovals: vi.fn(),
    secretBoundary: vi.fn(),
    rejectApproval: vi.fn(),
    list: vi.fn(async () => ({ refs: [] })),
    setNotes: vi.fn(async () => ({})),
  },
}));

const { agentsState, engineState, listModels } = vi.hoisted(() => ({
  agentsState: { data: [] as unknown[] },
  engineState: { data: { model: null, transcribe_model: null } as Record<string, unknown> },
  listModels: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => agentsState }));
vi.mock("@/lib/hooks/useInternalEngine", () => ({ useInternalEngineConfig: () => engineState }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useEndpointModels: () => ({
    data: { models: [], message: "", reachable: true },
    error: null,
    isPending: false,
    isFetching: false,
    dataUpdatedAt: 0,
    refetch: vi.fn(),
  }),
  useListProviderModels: () => ({ mutateAsync: listModels, isPending: false }),
}));

const { providersApi } = await import("@/lib/api/providers");
const { scopeApi } = await import("@/lib/api/scope");
const { secretsApi } = await import("@/lib/api/secret");
const api = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const UIDS: Record<string, string> = {
  official: "cn-7ba2",
  agnes: "cn-c94d",
  groq: "cn-41aa",
  myconn: "cn-0e58",
  "local-llm": "cn-6a11",
};

const makeProvider = (over: Partial<Provider> = {}): Provider => {
  const name = over.name ?? "official";
  return {
    uid: UIDS[name] ?? `cn-${name}`,
    name,
    title: null,
    protocol: "anthropic",
    base_url: "https://gw/anthropic",
    secret_ref: `provider/${name}/key`,
    local_runtime: null,
    compatible_agents: ["claude_code"],
    served_agents: ["claude_code"],
    anthropic_base_url: null,
    transcribe_default: false,
    models: [],
    enabled: true,
    description: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
};

const agent = (
  type: "claude_code" | "codex",
  model: string | null = null,
  connection_uid: string | null = null,
): AgentOut =>
  ({
    uid: `a-${type}`,
    type,
    name: type,
    display_name: type === "codex" ? "Codex" : "Claude Code",
    model,
    connection_uid,
    config_dir: type === "codex" ? "/Users/me/.codex" : "/Users/me/.claude",
  }) as AgentOut;

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

function renderAt(path = "/model-providers") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/model-providers" element={<ModelProvidersPage />} />
          <Route path="/model-providers/:uid" element={<ModelProvidersPage />} />
          <Route path="/model-providers/:uid/:tab" element={<ModelProvidersPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const rowFor = (name: string) =>
  screen.getAllByTestId("provider-row").find((r) => r.textContent?.includes(name)) as HTMLElement;
const where = () => screen.getByTestId("where").textContent;

function serve(providers: Provider[]) {
  api.list.mockResolvedValue({ providers });
  api.get.mockImplementation(async (uid: string) => {
    const hit = providers.find((p) => p.uid === uid);
    if (!hit) throw new Error("not found");
    return hit;
  });
}

async function openAdd() {
  fireEvent.click(await screen.findByRole("button", { name: "Add provider" }));
  return within(await screen.findByRole("dialog"));
}

describe("ModelProvidersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    agentsState.data = [];
    engineState.data = { model: null, transcribe_model: null };
    (scopeApi.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      scope: null,
      supports_scope: true,
    });
    (secretsApi.pendingApprovals as ReturnType<typeof vi.fn>).mockResolvedValue({
      approvals: [],
    });
    api.health.mockResolvedValue({ connections: [] });
  });

  acceptance(
    "provider-switching",
    "a connection that never opened is marked in the list",
    async () => {
      serve([
        makeProvider({ name: "official" }),
        makeProvider({ name: "agnes", protocol: "openai" }),
        makeProvider({ name: "groq", protocol: "openai" }),
      ]);
      const verdict = (uid: string, status: string) => ({
        uid,
        status,
        checked_at: "2026-10-09T02:00:00Z",
        since: "2026-10-09T01:00:00Z",
        source: "check",
        message: status === "reachable" ? "" : "Error code: 401",
      });
      api.health.mockResolvedValue({
        connections: [
          verdict(UIDS.agnes, "key_rejected"),
          verdict(UIDS.groq, "unreachable"),
          verdict(UIDS.official, "reachable"),
        ],
      });
      renderAt();
      // The first provider opens, and its own probe answered: it reads normally.
      await waitFor(() => expect(rowFor("official")).toHaveAttribute("aria-current", "page"));
      // The rows nobody opened read the daemon's kept verdict, in red.
      await waitFor(() => expect(rowFor("agnes")).toHaveTextContent("Key rejected"));
      expect(rowFor("groq")).toHaveTextContent("Unreachable");
      expect(rowFor("agnes").querySelector(".text-danger")).toHaveTextContent("Key rejected");
      expect(rowFor("official")).toHaveTextContent("Anthropic · all models");
    },
  );

  acceptance(
    "provider-switching",
    "the connections page lists profiles and their compatible agents",
    async () => {
      agentsState.data = [agent("claude_code", "claude-opus-4-1", UIDS.official)];
      serve([
        makeProvider({ name: "official", compatible_agents: ["claude_code"] }),
        makeProvider({
          name: "agnes",
          protocol: "openai",
          base_url: "https://apihub.agnes-ai.com/v1",
          compatible_agents: ["codex"],
        }),
      ]);
      renderAt();

      // Both providers are listed, and the address opens the first one.
      await waitFor(() => expect(where()).toBe(`/model-providers/${UIDS.official}`));
      await waitFor(() => expect(rowFor("official")).toHaveAttribute("aria-current", "page"));
      expect(rowFor("agnes")).toBeInTheDocument();
      // The active one is marked by the agent running on it.
      expect(within(rowFor("official")).getByRole("img", { name: "Claude Code" })).toBeTruthy();
      expect(within(rowFor("agnes")).queryByRole("img", { name: "Claude Code" })).toBeNull();
      // The open provider shows its address, and the agents its addresses serve.
      expect(await screen.findAllByText("https://gw/anthropic")).not.toHaveLength(0);
      expect(screen.getByTestId("provider-header")).toHaveTextContent("For Claude Code");
      // No per-row "Switch": activation is per agent, on its Model tab.
      expect(screen.queryByRole("button", { name: /^switch/i })).toBeNull();
      expect(api.activate).not.toHaveBeenCalled();
    },
  );

  acceptance(
    "provider-switching",
    "the library names the connections Coffer itself uses",
    async () => {
      serve([
        makeProvider({ name: "official" }),
        makeProvider({ name: "agnes" }),
        makeProvider({ name: "groq", transcribe_default: true }),
      ]);
      renderAt();
      await screen.findAllByTestId("provider-row");

      const badge = (row: string, name: string | RegExp) =>
        within(rowFor(row)).queryByRole("img", { name });
      expect(badge("groq", "Coffer · speech to text")).toBeTruthy();
      expect(badge("agnes", /^Coffer · /)).toBeNull();
      expect(badge("official", /^Coffer · /)).toBeNull();
    },
  );

  acceptance("provider-switching", "the provider library has no tabs", async () => {
    serve([makeProvider({ name: "official" })]);
    renderAt();
    // The open provider is one column — Used by, Endpoint, Models — and the
    // only tab strip is the page header's Providers | Usage.
    expect(await screen.findByRole("heading", { name: "Endpoint" })).toBeInTheDocument();
    expect(screen.getAllByRole("tablist")).toHaveLength(1);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Providers", "Usage"]);
  });

  acceptance("provider-switching", "Usage is a tab of Model providers", async () => {
    serve([makeProvider({ name: "official" })]);
    renderAt();
    expect(await screen.findByRole("heading", { name: "Model providers" })).toBeInTheDocument();
    // The header carries no Experimental tag, and the primary button for both
    // tabs.
    expect(screen.queryByText("Experimental")).toBeNull();
    expect(
      screen.getByText(
        "Where your agents’ models come from, and what requests through Coffer cost.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add provider/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Providers" })).toHaveAttribute("aria-selected", "true");
    // Radix tabs switch on mousedown.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Usage" }));
    await waitFor(() => expect(where()).toBe("/model-providers?tab=usage"));
    expect(await screen.findByText("usage tab body")).toBeInTheDocument();
    // The header, with its Add provider, is the same one on both tabs.
    expect(screen.getByRole("button", { name: /Add provider/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Endpoint" })).toBeNull();
  });

  test("?provider= opens that provider and hands ?model= to its Models search", async () => {
    serve([
      makeProvider({ name: "official" }),
      makeProvider({ name: "agnes", protocol: "openai" }),
    ]);
    renderAt(`/model-providers?provider=${UIDS.agnes}&model=gpt-9`);
    await waitFor(() => expect(where()).toBe(`/model-providers/${UIDS.agnes}?model=gpt-9`));
    await waitFor(() => expect(rowFor("agnes")).toHaveAttribute("aria-current", "page"));
  });

  test("a row says what the provider offers", async () => {
    serve([
      makeProvider({ name: "official", models: [{ id: "a" }, { id: "b" }] as ProviderModel[] }),
      makeProvider({ name: "agnes", protocol: "openai" }),
      makeProvider({ name: "local-llm", protocol: "ollama", secret_ref: null }),
    ]);
    renderAt();
    await screen.findAllByTestId("provider-row");
    expect(rowFor("official")).toHaveTextContent("Anthropic · 2 models");
    expect(rowFor("agnes")).toHaveTextContent("OpenAI-compatible · all models");
    expect(rowFor("local-llm")).toHaveTextContent("Ollama · all models");
  });

  test("the list is folded by dragging its divider, not by a button", async () => {
    serve([makeProvider({ name: "official" })]);
    renderAt();
    await screen.findAllByTestId("provider-row");
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /hide list/i })).toBeNull();
  });

  test("the filter narrows the rows by name, not by endpoint", async () => {
    serve([
      makeProvider({ name: "official" }),
      makeProvider({ name: "agnes", base_url: "https://apihub.agnes-ai.com/v1" }),
    ]);
    renderAt();
    await screen.findAllByTestId("provider-row");
    fireEvent.change(screen.getByRole("textbox", { name: "Filter providers" }), {
      target: { value: "agn" },
    });
    expect(screen.getAllByTestId("provider-row")).toHaveLength(1);
    expect(rowFor("agnes")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Filter providers" }), {
      target: { value: "apihub" },
    });
    expect(screen.queryAllByTestId("provider-row")).toHaveLength(0);
  });

  test("the header stays up while loading, and an empty library is the first-run state", async () => {
    let resolve: (v: { providers: Provider[] }) => void = () => {};
    api.list.mockReturnValue(new Promise((r) => (resolve = r)));
    agentsState.data = [agent("claude_code"), agent("codex")];
    renderAt();
    expect(screen.getByRole("heading", { name: "Model providers" })).toBeInTheDocument();

    resolve({ providers: [] });
    expect(await screen.findByText("No model providers yet")).toBeInTheDocument();
    // An option card opens Add on its preset: the local runtime path is keyless.
    api.detectLocal.mockResolvedValue({ found: [] });
    fireEvent.click(screen.getByRole("button", { name: /A runtime on this Mac/ }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("radio", { name: "Ollama" })).toHaveAttribute("aria-checked", "true");
    expect(dialog.queryByLabelText("API key")).toBeNull();
  });

  test("Add with Custom: fill both addresses, test the unsaved key, choose models, add", async () => {
    serve([]);
    api.create.mockResolvedValue(makeProvider({ name: "myconn", protocol: "openai" }));
    listModels.mockResolvedValue({
      models: [
        { id: "gpt-5", modality: "text" },
        { id: "text-embedding-3-large", modality: "embedding" },
      ],
      message: "",
      reachable: true,
    });
    renderAt();
    const dialog = await openAdd();

    fireEvent.click(dialog.getByRole("radio", { name: "Custom" }));
    expect(dialog.queryByRole("radiogroup", { name: "Protocol" })).toBeNull();
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "myconn" } });
    fireEvent.change(dialog.getByLabelText("OpenAI-compatible address"), {
      target: { value: "https://gw/v1" },
    });
    fireEvent.change(dialog.getByLabelText("Anthropic-compatible address"), {
      target: { value: "https://gw" },
    });
    fireEvent.change(dialog.getByLabelText("API key"), { target: { value: "sk-x" } });
    fireEvent.click(dialog.getByRole("button", { name: "Test" }));

    // The test sends the unsaved key inline; nothing is saved yet.
    await waitFor(() => expect(listModels).toHaveBeenCalledTimes(1));
    expect(listModels.mock.calls[0][0]).toMatchObject({
      provider: "openai",
      base_url: "https://gw/v1",
      secret_value: "sk-x",
    });
    expect(await dialog.findByText(/^Connected in \d+ ms$/)).toBeInTheDocument();
    expect(api.create).not.toHaveBeenCalled();

    fireEvent.click(dialog.getByRole("button", { name: "Next: Models" }));
    expect(await dialog.findByText("0 of 2 selected")).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("checkbox", { name: "gpt-5" }));
    fireEvent.click(dialog.getByRole("button", { name: "Add provider" }));

    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    const body = api.create.mock.calls[0][0];
    expect(body).toEqual({
      name: "myconn",
      protocol: "openai",
      base_url: "https://gw/v1",
      anthropic_base_url: "https://gw",
      secret_value: "sk-x",
      models: [{ id: "gpt-5", modality: "text" }],
    });
    // Reach is the resource's scope, never a create field.
    expect(body).not.toHaveProperty("compatible_agents");
    await waitFor(() => expect(where()).toBe(`/model-providers/${UIDS.myconn}`));
  });

  acceptance("web-ui", "an add form picks a stored secret or takes a new one", async () => {
    serve([]);
    vi.mocked(secretsApi.list).mockResolvedValue({
      refs: [
        {
          ref: `secret/${"c3".repeat(16)}`,
          label: "Team gateway key",
          present: true,
          cited_by: [],
          bindings: [],
          mentioned_by_skills: [],
          uri: null,
        },
      ],
    } as never);
    api.create.mockResolvedValue(makeProvider({ name: "gw", protocol: "openai" }));
    listModels.mockResolvedValue({ models: [], message: "", reachable: true });
    renderAt();
    const dialog = await openAdd();

    fireEvent.click(dialog.getByRole("radio", { name: "Custom" }));
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "gw" } });
    fireEvent.change(dialog.getByLabelText("OpenAI-compatible address"), {
      target: { value: "https://gw/v1" },
    });
    // The key field's menu lists what Secrets holds; picking one cites it, nothing is pasted.
    fireEvent.click(dialog.getByRole("button", { name: "Choose a secret for API key" }));
    fireEvent.click(await screen.findByRole("option", { name: /Team gateway key/ }));
    fireEvent.click(dialog.getByRole("button", { name: "Test" }));

    await waitFor(() => expect(listModels).toHaveBeenCalledTimes(1));
    expect(listModels.mock.calls[0][0]).toMatchObject({ secret_ref: `secret/${"c3".repeat(16)}` });
    expect(listModels.mock.calls[0][0]).not.toHaveProperty("secret_value");
  });

  test("Add validates inline and shows a rejected key", async () => {
    serve([]);
    listModels.mockResolvedValue({
      models: [],
      message: "Client error '401 Unauthorized' for url 'https://gw/v1/models'",
      reachable: false,
    });
    renderAt();
    const dialog = await openAdd();
    fireEvent.click(dialog.getByRole("radio", { name: "Custom" }));
    fireEvent.change(dialog.getByLabelText("OpenAI-compatible address"), {
      target: { value: "gw.example" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Next: Models" }));
    expect(await dialog.findByText("Enter a name.")).toBeInTheDocument();
    expect(
      dialog.getByText("Enter a full URL, e.g. https://api.openai.com/v1"),
    ).toBeInTheDocument();
    expect(dialog.getByText("Enter the API key.")).toBeInTheDocument();

    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "gw" } });
    fireEvent.change(dialog.getByLabelText("OpenAI-compatible address"), {
      target: { value: "https://gw/v1" },
    });
    fireEvent.change(dialog.getByLabelText("API key"), { target: { value: "bad" } });
    fireEvent.click(dialog.getByRole("button", { name: "Test" }));
    expect(await dialog.findByText("The endpoint rejected the key (401)")).toBeInTheDocument();
    expect(dialog.getByText(/Nothing was saved/)).toBeInTheDocument();
  });

  acceptance("provider-switching", "create a keyless local runtime connection", async () => {
    serve([]);
    api.detectLocal.mockResolvedValue({ found: [] });
    renderAt();
    const dialog = await openAdd();

    fireEvent.click(dialog.getByRole("radio", { name: "Ollama" }));
    // The local path is keyless: no API key field at all.
    expect(dialog.queryByLabelText("API key")).toBeNull();
    await waitFor(() => expect(api.detectLocal).toHaveBeenCalledWith(null));
    // Nothing answered: no Name, no protocol to pick, and Next waits for a runtime even
    // with an address typed — an Ollama connection is only ever made from a detected runtime.
    expect(await dialog.findByText("Nothing answered on the default ports")).toBeInTheDocument();
    expect(dialog.queryByLabelText("Name")).toBeNull();
    fireEvent.change(dialog.getByLabelText("Base URL"), {
      target: { value: "http://localhost:11434" },
    });
    expect(dialog.queryByLabelText("Name")).toBeNull();
    expect(dialog.getByRole("button", { name: "Next: Models" })).toBeDisabled();
    expect(dialog.queryByText("Ollama API")).toBeNull();
    expect(api.create).not.toHaveBeenCalled();
  });

  test("a detected runtime is recorded with its tool-capable models and their windows", async () => {
    serve([]);
    api.detectLocal.mockResolvedValue({
      found: [
        {
          base_url: "http://127.0.0.1:11434",
          runtime: { runtime: "ollama", version: "0.14.2", wires: ["anthropic", "openai"] },
          models: [
            { id: "qwen3-coder", context_window: 65536, tools: true },
            { id: "llava", context_window: 4096, tools: false },
          ],
        },
      ],
    });
    api.create.mockResolvedValue(makeProvider({ name: "local-llm", protocol: "anthropic" }));
    renderAt();
    const dialog = await openAdd();
    fireEvent.click(dialog.getByRole("radio", { name: "Ollama" }));

    expect(await dialog.findByText(/Ollama 0\.14\.2/)).toBeInTheDocument();
    // The chosen runtime names the provider; the first wire it serves is used.
    expect(dialog.getByLabelText("Name")).toHaveValue("Ollama · this Mac");
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "local-llm" } });
    fireEvent.click(dialog.getByRole("button", { name: "Next: Models" }));

    // Tool-capable models start selected; one that cannot call tools does not.
    expect(await dialog.findByRole("checkbox", { name: "qwen3-coder" })).toBeChecked();
    expect(dialog.getByRole("checkbox", { name: "llava" })).not.toBeChecked();
    fireEvent.click(dialog.getByRole("button", { name: "Add provider" }));

    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    expect(api.create.mock.calls[0][0]).toEqual({
      name: "local-llm",
      protocol: "anthropic",
      base_url: "http://127.0.0.1:11434",
      local_runtime: { runtime: "ollama", version: "0.14.2", wires: ["anthropic", "openai"] },
      models: [{ id: "qwen3-coder", modality: "text", context_window: 65536 }],
    });
  });
});
