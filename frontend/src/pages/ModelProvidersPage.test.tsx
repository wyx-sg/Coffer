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
import { ProviderDetailPage } from "./ProviderDetailPage";

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
  },
}));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn(), rename: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/api/credentials", () => ({
  credentialsApi: { pendingApprovals: vi.fn(), secretBoundary: vi.fn(), rejectApproval: vi.fn() },
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
const { credentialsApi } = await import("@/lib/api/credentials");
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
    credential_ref: `provider/${name}/key`,
    local_runtime: null,
    compatible_agents: ["claude_code"],
    is_active: false,
    internal_default: false,
    transcribe_default: false,
    models: [],
    enabled: true,
    description: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
};

const agent = (type: "claude_code" | "codex", model: string | null = null): AgentOut =>
  ({
    uid: `a-${type}`,
    type,
    name: type,
    display_name: type === "codex" ? "Codex" : "Claude Code",
    model,
    config_dir: type === "codex" ? "/Users/me/.codex" : "/Users/me/.claude",
  }) as AgentOut;

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname}</output>;
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
          <Route path="/model-providers/:uid" element={<ProviderDetailPage />} />
          <Route path="/model-providers/:uid/:tab" element={<ProviderDetailPage />} />
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
    (credentialsApi.pendingApprovals as ReturnType<typeof vi.fn>).mockResolvedValue({
      approvals: [],
    });
  });

  acceptance(
    "provider-switching",
    "the connections page lists profiles and their compatible agents",
    async () => {
      agentsState.data = [agent("claude_code", "claude-opus-4-1")];
      serve([
        makeProvider({ name: "official", is_active: true, compatible_agents: ["claude_code"] }),
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
      // The open provider shows its endpoint, and its reach in the shared control.
      expect(await screen.findAllByText("https://gw/anthropic")).not.toHaveLength(0);
      expect(screen.getByTestId("scope-control")).toBeInTheDocument();
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
        makeProvider({ name: "agnes", internal_default: true }),
        makeProvider({ name: "groq", transcribe_default: true }),
      ]);
      renderAt();
      await screen.findAllByTestId("provider-row");

      const badge = (row: string, name: string | RegExp) =>
        within(rowFor(row)).queryByRole("img", { name });
      expect(badge("agnes", "Coffer · background model")).toBeTruthy();
      expect(badge("agnes", "Coffer · speech to text")).toBeNull();
      expect(badge("groq", "Coffer · speech to text")).toBeTruthy();
      expect(badge("groq", "Coffer · background model")).toBeNull();
      expect(badge("official", /^Coffer · /)).toBeNull();
    },
  );

  test("the provider library has no tabs", async () => {
    // Scenario (revise-web-ui-ia): "the provider library has no tabs"
    serve([makeProvider({ name: "official" })]);
    renderAt();
    await screen.findByRole("tab", { name: /overview/i });
    // The one tab strip is the open provider's own Overview | Models — no
    // "who runs on what" view and no Coffer's model tab on the library.
    expect(screen.getAllByRole("tablist")).toHaveLength(1);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Overview", "Models"]);
    expect(screen.queryByRole("tab", { name: /who runs|coffer's model/i })).toBeNull();
  });

  test("a row says what the provider offers", async () => {
    serve([
      makeProvider({ name: "official", models: [{ id: "a" }, { id: "b" }] as ProviderModel[] }),
      makeProvider({ name: "agnes", protocol: "openai" }),
      makeProvider({ name: "local-llm", protocol: "ollama", credential_ref: null }),
    ]);
    renderAt();
    await screen.findAllByTestId("provider-row");
    expect(rowFor("official")).toHaveTextContent("Anthropic · 2 models");
    expect(rowFor("agnes")).toHaveTextContent("OpenAI-compatible · All models");
    expect(rowFor("local-llm")).toHaveTextContent("Ollama · Coffer's engine only");
  });

  test("the filter narrows the rows over name and endpoint", async () => {
    serve([
      makeProvider({ name: "official" }),
      makeProvider({ name: "agnes", base_url: "https://apihub.agnes-ai.com/v1" }),
    ]);
    renderAt();
    await screen.findAllByTestId("provider-row");
    fireEvent.change(screen.getByRole("textbox", { name: "Filter" }), {
      target: { value: "apihub" },
    });
    expect(screen.getAllByTestId("provider-row")).toHaveLength(1);
    expect(rowFor("agnes")).toBeInTheDocument();
  });

  test("the header stays up while loading, and an empty library is the welcome panel", async () => {
    let resolve: (v: { providers: Provider[] }) => void = () => {};
    api.list.mockReturnValue(new Promise((r) => (resolve = r)));
    agentsState.data = [agent("claude_code"), agent("codex")];
    renderAt();
    expect(screen.getByRole("heading", { name: "Model providers" })).toBeInTheDocument();

    resolve({ providers: [] });
    expect(await screen.findByText("Bring your own model endpoint")).toBeInTheDocument();
    // What each registered agent runs on now: its own login.
    expect(screen.getByText("Own login (Anthropic)")).toBeInTheDocument();
    expect(screen.getByText("Own login (ChatGPT)")).toBeInTheDocument();
    // No provider carries Coffer's engine, so say what that pauses.
    expect(
      screen.getByText("Coffer's model isn't set, so distil and curation are paused."),
    ).toBeInTheDocument();
    // An option card opens Add on its preset: the local runtime path is keyless.
    api.detectLocal.mockResolvedValue({ found: [] });
    fireEvent.click(screen.getByRole("button", { name: /A local runtime on this Mac/ }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("radio", { name: "Ollama" })).toHaveAttribute("aria-checked", "true");
    expect(dialog.queryByLabelText("API key")).toBeNull();
  });

  test("Add with Custom: pick the protocol, test the unsaved key, choose models, add", async () => {
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
    fireEvent.click(dialog.getByRole("radio", { name: /^OpenAI-compatible/ }));
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "myconn" } });
    fireEvent.change(dialog.getByLabelText("Base URL"), { target: { value: "https://gw/v1" } });
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

    fireEvent.click(dialog.getByRole("button", { name: "Next: models" }));
    expect(
      await dialog.findByText("0 selected · nothing selected means all 2 are offered"),
    ).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("checkbox", { name: "gpt-5" }));
    fireEvent.click(dialog.getByRole("button", { name: "Add provider" }));

    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    const body = api.create.mock.calls[0][0];
    expect(body).toEqual({
      name: "myconn",
      protocol: "openai",
      base_url: "https://gw/v1",
      secret_value: "sk-x",
      models: [{ id: "gpt-5", modality: "text" }],
    });
    // Reach is the resource's scope, never a create field.
    expect(body).not.toHaveProperty("compatible_agents");
    await waitFor(() => expect(where()).toBe(`/model-providers/${UIDS.myconn}`));
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
    fireEvent.change(dialog.getByLabelText("Base URL"), { target: { value: "gw.example" } });
    fireEvent.click(dialog.getByRole("button", { name: "Next: models" }));
    expect(await dialog.findByText("Enter a name.")).toBeInTheDocument();
    expect(
      dialog.getByText("Enter a full URL, e.g. https://api.openai.com/v1"),
    ).toBeInTheDocument();
    expect(dialog.getByText("Enter the API key.")).toBeInTheDocument();

    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "gw" } });
    fireEvent.change(dialog.getByLabelText("Base URL"), { target: { value: "https://gw/v1" } });
    fireEvent.change(dialog.getByLabelText("API key"), { target: { value: "bad" } });
    fireEvent.click(dialog.getByRole("button", { name: "Test" }));
    expect(await dialog.findByText("The endpoint rejected the key (401)")).toBeInTheDocument();
    expect(dialog.getByText(/Nothing was saved/)).toBeInTheDocument();
  });

  acceptance("provider-switching", "create an ollama connection without a credential", async () => {
    serve([]);
    api.detectLocal.mockResolvedValue({ found: [] });
    api.create.mockResolvedValue(
      makeProvider({ name: "local-llm", protocol: "ollama", credential_ref: null }),
    );
    renderAt();
    const dialog = await openAdd();

    fireEvent.click(dialog.getByRole("radio", { name: "Ollama" }));
    // The local path is keyless: no API key field at all.
    expect(dialog.queryByLabelText("API key")).toBeNull();
    await waitFor(() => expect(api.detectLocal).toHaveBeenCalledWith(null));
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "local-llm" } });
    fireEvent.click(dialog.getByRole("button", { name: "Next: models" }));
    fireEvent.click(await dialog.findByRole("button", { name: "Add provider" }));

    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    const body = api.create.mock.calls[0][0];
    expect(body).toMatchObject({
      name: "local-llm",
      protocol: "ollama",
      base_url: "http://localhost:11434",
    });
    expect(body.secret_value).toBeUndefined();
    expect(body.credential_ref).toBeUndefined();
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
    fireEvent.click(dialog.getByRole("radio", { name: /^Anthropic-compatible/ }));
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "local-llm" } });
    fireEvent.click(dialog.getByRole("button", { name: "Next: models" }));

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
