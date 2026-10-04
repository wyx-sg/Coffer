// src/pages/ProviderDetailPage.test.tsx — one provider: header, Overview (Used by, Endpoint, Models), Models tab, dialogs.
//
// The endpoint probe runs when the provider opens and feeds the header's
// health, the key-rejected banner and the Models tab, which curates the set
// with PATCH {models} — one row per model with its switch and type, a failed
// probe saying so with a Retry and leaving the selection alone. Used by is
// read-only and links where each use is changed. Edit renames through the
// kind-agnostic route first; Replace key waits for approval when the key is
// in use; Delete is blocked while anything runs on the provider.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AgentOut } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";
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
    deletePreview: vi.fn(),
    activate: vi.fn(),
    detectLocal: vi.fn(),
  },
}));
vi.mock("@/components/usage/UsageTab", () => ({ UsageTab: () => <p>usage tab body</p> }));
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn(), rename: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({ scopeApi: { get: vi.fn(), put: vi.fn() } }));
vi.mock("@/lib/api/secret", () => ({
  secretsApi: { pendingApprovals: vi.fn(), secretBoundary: vi.fn(), rejectApproval: vi.fn() },
}));

type EndpointState = {
  data?: { models: ProviderModel[]; message: string; reachable: boolean };
  error?: unknown;
  isPending?: boolean;
  isFetching?: boolean;
};
const { agentsState, engineState, refetch, probedFor, endpoint, listModels } = vi.hoisted(() => ({
  agentsState: { data: [] as unknown[] },
  engineState: { data: { model: null, transcribe_model: null } as Record<string, unknown> },
  refetch: vi.fn(),
  probedFor: [] as string[],
  endpoint: { state: {} as Record<string, unknown> },
  listModels: vi.fn(),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => agentsState }));
vi.mock("@/lib/hooks/useInternalEngine", () => ({ useInternalEngineConfig: () => engineState }));
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useEndpointModels: (uid: string) => {
    if (uid) probedFor.push(uid);
    return {
      data: undefined,
      error: null,
      isPending: false,
      isFetching: false,
      dataUpdatedAt: 0,
      refetch,
      ...endpoint.state,
    };
  },
  useListProviderModels: () => ({ mutateAsync: listModels, isPending: false }),
}));

const { providersApi } = await import("@/lib/api/providers");
const { resourcesApi } = await import("@/lib/api/resources");
const { scopeApi } = await import("@/lib/api/scope");
const { secretsApi } = await import("@/lib/api/secret");
const api = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const resources = resourcesApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const pendingApprovals = secretsApi.pendingApprovals as ReturnType<typeof vi.fn>;

const UID = "cn-31f0";
const makeProvider = (over: Partial<Provider> = {}): Provider => ({
  uid: UID,
  name: "acme",
  title: null,
  protocol: "openai",
  base_url: "https://gw/v1",
  secret_ref: "provider/acme",
  local_runtime: null,
  compatible_agents: ["codex"],
  internal_default: false,
  transcribe_default: false,
  fallback: true,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});
const chat = (...ids: string[]): ProviderModel[] => ids.map((id) => ({ id, modality: "text" }));
// The agent runs on the provider under test (UID) — its record names it.
const agent = (type: "claude_code" | "codex", model: string | null): AgentOut =>
  ({
    uid: `a-${type}`,
    type,
    name: type,
    display_name: type === "codex" ? "Codex" : "Claude Code",
    model,
    connection_uid: UID,
  }) as AgentOut;

function setEndpoint(state: EndpointState) {
  endpoint.state = state as Record<string, unknown>;
}
const serves = (models: ProviderModel[], message = "") =>
  setEndpoint({ data: { models, message, reachable: true } });

function serve(provider: Provider) {
  api.list.mockResolvedValue({ providers: [provider] });
  api.get.mockResolvedValue(provider);
}

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

function renderPage(path = `/model-providers/${UID}`) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/model-providers" element={<ModelProvidersPage />} />
          <Route path="/model-providers/:uid" element={<ModelProvidersPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const where = () => screen.getByTestId("where").textContent;
const switchFor = (id: string) => screen.getByRole("switch", { name: `Offered: ${id}` });
const typePickerFor = (id: string) => screen.getByRole("button", { name: `Type: ${id}` });
const heading = () => screen.findByRole("heading", { name: "acme", level: 2 });

describe("ProviderDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    probedFor.length = 0;
    setEndpoint({});
    agentsState.data = [];
    engineState.data = { model: null, transcribe_model: null };
    (scopeApi.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      scope: null,
      supports_scope: true,
    });
    pendingApprovals.mockResolvedValue({ approvals: [] });
  });

  acceptance("provider-switching", "a provider's used-by list is read-only", async () => {
    agentsState.data = [agent("claude_code", "claude-opus-4-1")];
    engineState.data = { model: "gpt-5-mini", transcribe_model: null };
    serve(
      makeProvider({
        protocol: "anthropic",
        compatible_agents: ["claude_code"],
        internal_default: true,
      }),
    );
    renderPage();
    await heading();

    const usedBy = screen.getByRole("heading", { name: "Used by" }).closest("section")!;
    // Each row links to where it is changed: the agent's Change model, or Settings.
    const claude = within(usedBy).getByRole("link", { name: "Claude Code › Change model" });
    expect(claude).toHaveAttribute("href", "/agents/claude_code?change-model=1");
    expect(within(usedBy).getByText("claude-opus-4-1")).toBeInTheDocument();
    expect(within(usedBy).getByText("gpt-5-mini")).toBeInTheDocument();
    // A healthy row carries no status word.
    expect(within(usedBy).queryByText(/Runs on this provider|Requests fail/)).toBeNull();
    const engine = within(usedBy).getByRole("button", { name: "Settings › General" });
    // No switch, activate or revert control in Used by.
    expect(within(usedBy).queryByRole("switch")).toBeNull();
    expect(
      within(usedBy).queryByRole("button", { name: /switch|activate|revert|built-in|own login/i }),
    ).toBeNull();
    fireEvent.click(engine);
    await waitFor(() => expect(where()).toBe("/settings/general"));
  });

  test("the Overview names the endpoint, the key's secret and the offered models", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    serves(chat("gpt-5", "gpt-5-codex", "o4-mini"));
    serve(makeProvider({ models: chat("gpt-5", "gpt-5-codex") }));
    renderPage();
    await heading();

    expect(screen.getByText("Reachable")).toBeInTheDocument();
    expect(screen.getByText("locked while Codex runs on it")).toBeInTheDocument();
    // An opaque ref shows as itself; only a standalone secret has a coffer:// URI.
    expect(screen.getByText("provider/acme")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Secrets" })).toHaveAttribute("href", "/secrets");
    expect(screen.queryByText("2 of 3 offered")).not.toBeInTheDocument();
    // One column, no tabs: the Models section sits under Used by and Endpoint.
    // Only the page header's Providers | Usage tabs: the provider itself has none.
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Providers", "Usage"]);
    expect(screen.getByRole("switch", { name: /gpt-5-codex/ })).toBeInTheDocument();
  });

  test("the detail is three plain sections with a one-line header and unwrapped model names", async () => {
    serves(chat("gpt-5", "gpt-5-codex"));
    serve(makeProvider({ models: chat("gpt-5", "gpt-5-codex") }));
    const { container } = renderPage();
    await heading();

    // Used by, Endpoint and Models are plain Sections (title + a line + hairline rows), not cards.
    for (const name of ["Used by", "Endpoint", "Models"]) {
      const section = screen.getByRole("heading", { name }).closest("section")!;
      expect(section).not.toHaveClass("border");
    }
    // The header holds the actions in the sibling order: reach, test, edit, menu.
    const header = screen.getByTestId("provider-header");
    expect(within(header).getByTestId("scope-control")).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "Test" })).toBeInTheDocument();
    expect(within(header).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(
      within(header).getByRole("button", { name: "More actions for acme" }),
    ).toBeInTheDocument();
    // The menu holds only Delete: Refresh models is the Models section's button.
    fireEvent.click(within(header).getByRole("button", { name: "More actions for acme" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Delete provider"]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    // The page is no longer wrapped in one bordered box.
    expect(container.querySelector(".rounded-xl.border.overflow-hidden")).toBeNull();
    // A model name never wraps.
    expect(await screen.findByText("gpt-5-codex")).toHaveClass("whitespace-nowrap");
    expect(screen.getAllByTestId("model-row")).toHaveLength(2);
  });

  test("a keyless provider says no key is needed", async () => {
    serve(makeProvider({ protocol: "ollama", secret_ref: null, compatible_agents: [] }));
    renderPage();
    await heading();
    expect(screen.getByText("No key needed — this provider takes none.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Replace key" })).toBeNull();
  });

  acceptance(
    "provider-switching",
    "the models table lists the endpoint's models when it opens",
    async () => {
      serve(makeProvider());
      serves(chat("gpt-5", "gpt-5-codex"));
      renderPage();
      await heading();

      // Opening the provider IS the probe — there is no button to press.
      expect(probedFor).toContain(UID);
      expect(await screen.findByText("gpt-5-codex")).toBeInTheDocument();
      expect(switchFor("gpt-5")).toBeInTheDocument();
      expect(switchFor("gpt-5-codex")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /fetch models/i })).toBeNull();
    },
  );

  test("an empty selection shows every listed model switched on; narrowing writes the rest", async () => {
    serve(makeProvider({ models: [] }));
    api.update.mockResolvedValue(makeProvider());
    serves(chat("gpt-5", "gpt-5-codex"));
    renderPage();
    await screen.findByText("gpt-5-codex");

    expect(switchFor("gpt-5")).toBeChecked();
    expect(switchFor("gpt-5-codex")).toBeChecked();
    fireEvent.click(switchFor("gpt-5"));
    await waitFor(() => expect(api.update).toHaveBeenCalledTimes(1));
    expect(api.update).toHaveBeenCalledWith(UID, { models: chat("gpt-5-codex") });
  });

  acceptance(
    "provider-switching",
    "curate an embedding model alongside chat models on one connection",
    async () => {
      serve(makeProvider({ models: chat("gpt-4o") }));
      api.update.mockResolvedValue(makeProvider());
      serves([
        { id: "gpt-4o", modality: "text" },
        { id: "text-embedding-3-large", modality: "embedding" },
      ]);
      renderPage();
      await screen.findByText("text-embedding-3-large");

      // The probe's guess pre-fills each row's type.
      expect(typePickerFor("gpt-4o")).toHaveTextContent("Text / chat");
      expect(typePickerFor("text-embedding-3-large")).toHaveTextContent("Embedding");
      // The type is quiet text with a menu, not a bordered field.
      expect(typePickerFor("gpt-4o")).not.toHaveClass("border");

      fireEvent.click(switchFor("text-embedding-3-large"));
      await waitFor(() => expect(api.update).toHaveBeenCalledTimes(1));
      expect(api.update).toHaveBeenCalledWith(UID, {
        models: [
          { id: "gpt-4o", modality: "text" },
          { id: "text-embedding-3-large", modality: "embedding" },
        ],
      });
    },
  );

  test("the type filter narrows the rows", async () => {
    serve(makeProvider());
    serves([
      { id: "gpt-5", modality: "text" },
      { id: "whisper-1", modality: "audio" },
    ]);
    renderPage();
    await screen.findByText("whisper-1");
    fireEvent.click(screen.getByRole("button", { name: "Type" }));
    fireEvent.click(await screen.findByRole("option", { name: "Audio" }));
    expect(screen.queryByText("gpt-5")).toBeNull();
    expect(screen.getByText("whisper-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Type: Audio" }));
    fireEvent.click(await screen.findByRole("option", { name: "All" }));
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "a failed model introspection says so, with Refresh in the title",
    async () => {
      serve(makeProvider({ models: chat("hand-typed-model") }));
      setEndpoint({ error: new ApiError("INTERNAL_ERROR", "endpoint refused") });
      renderPage();

      expect(await screen.findByText("Couldn't list this endpoint's models")).toBeInTheDocument();
      expect(screen.getByText("Listing failed")).toBeInTheDocument();
      // The box has no Retry of its own: Refresh is the title's.
      expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
      // The curated list survives the failed probe.
      expect(switchFor("hand-typed-model")).toBeChecked();
      expect(api.update).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
      expect(refetch).toHaveBeenCalledTimes(1);
    },
  );

  test("an endpoint that lists nothing says what that means", async () => {
    serve(makeProvider({ models: [] }));
    serves([], "the endpoint listed no models");
    renderPage();
    expect(await screen.findByText("This endpoint listed no models")).toBeInTheDocument();
  });

  test("a rejected key shows in the header and in the Endpoint box, not row by row", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    serve(makeProvider());
    setEndpoint({
      data: {
        models: [],
        message: "Client error '401 Unauthorized' for url 'https://gw/v1/models'",
        reachable: false,
      },
    });
    renderPage();
    await heading();
    expect(screen.getAllByText("Key rejected").length).toBeGreaterThan(0);
    expect(screen.getByText("The endpoint rejects the stored key (401)")).toBeInTheDocument();
    expect(
      screen.getByText("Everything that uses it fails until you replace the key."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Requests fail/)).toBeNull();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    // Replace key lives in the box only, not on the key row as well.
    expect(screen.getAllByRole("button", { name: "Replace key…" })).toHaveLength(1);
  });

  test("Edit renames first, then patches the endpoint; the protocol is locked while live", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    const provider = makeProvider();
    serve(provider);
    resources.rename.mockResolvedValue(undefined);
    api.update.mockResolvedValue(provider);
    renderPage();
    await heading();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Locked while Codex runs on it.")).toBeInTheDocument();
    expect(dialog.getByRole("combobox", { name: "Protocol" })).toBeDisabled();
    expect(dialog.getByText("provider/acme")).toBeInTheDocument();
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "acme-eu" } });
    fireEvent.change(dialog.getByLabelText("Base URL"), { target: { value: "https://gw/v2" } });
    fireEvent.click(dialog.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.update).toHaveBeenCalledTimes(1));
    expect(resources.rename).toHaveBeenCalledWith(UID, "acme-eu");
    expect(resources.rename.mock.invocationCallOrder[0]).toBeLessThan(
      api.update.mock.invocationCallOrder[0],
    );
    expect(api.update).toHaveBeenCalledWith(UID, { base_url: "https://gw/v2" });
    // The page stays where it is: its address is the uid.
    expect(where()).toBe(`/model-providers/${UID}`);
  });

  acceptance("web-ui", "a renamable kind keeps its uid in the address", async () => {
    // Renamed from `work` to `work-proxy`; the saved address carries the uid.
    serve(makeProvider({ name: "work-proxy" }));
    renderPage(`/model-providers/${UID}`);

    expect(
      await screen.findByRole("heading", { name: "work-proxy", level: 2 }),
    ).toBeInTheDocument();
    expect(where()).toBe(`/model-providers/${UID}`);
    expect(screen.queryByText(/not found/i)).toBeNull();
  });

  test("a taken name fails inline and nothing else is written", async () => {
    serve(makeProvider());
    resources.rename.mockRejectedValue(new ApiError("RESOURCE_ALREADY_EXISTS", "taken"));
    renderPage();
    await heading();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "taken" } });
    fireEvent.click(dialog.getByRole("button", { name: "Save" }));
    expect(await dialog.findByRole("alert")).toBeInTheDocument();
    expect(api.update).not.toHaveBeenCalled();
  });

  test("Replace key checks the pasted key, then stores it and closes", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    serve(makeProvider());
    api.update.mockResolvedValue(makeProvider());
    listModels.mockResolvedValue({ models: chat("gpt-5"), message: "", reachable: true });
    renderPage();
    await heading();

    fireEvent.click(screen.getByRole("button", { name: "Replace key…" }));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("New key"), { target: { value: "sk-new" } });
    // No Test button: the key is checked as it is pasted.
    expect(dialog.queryByRole("button", { name: "Test" })).toBeNull();
    await waitFor(() =>
      expect(listModels).toHaveBeenCalledWith(
        expect.objectContaining({ secret_value: "sk-new", base_url: "https://gw/v1" }),
      ),
    );
    expect(await dialog.findByText(/The new key works — 1 model listed/)).toBeInTheDocument();

    fireEvent.click(dialog.getByRole("button", { name: "Replace key" }));
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(UID, { secret_value: "sk-new" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("Deleting a provider Coffer's engine runs on names what changes, then deletes it", async () => {
    serve(makeProvider({ internal_default: true }));
    api.deletePreview.mockResolvedValue({ agents: [] });
    api.remove.mockResolvedValue(undefined);
    renderPage();
    await heading();
    fireEvent.click(screen.getByRole("button", { name: "More actions for acme" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete provider" }));
    // Not blocked: the consequence is said, and Delete is available. (The review
    // gives way to a plain confirmation once nothing in an agent's file changes.)
    expect(await screen.findByText(/Coffer’s engine pauses/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete provider" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith(UID));
  });

  acceptance(
    "provider-switching",
    "deleting a provider an agent runs on is a review of its config diff, and Delete applies it",
    async () => {
      agentsState.data = [agent("codex", "gpt-5-codex")];
      serve(makeProvider({ internal_default: true }));
      api.deletePreview.mockResolvedValue({
        agents: [
          {
            agent_uid: "a-codex",
            agent_type: "codex",
            agent_name: "codex",
            files: [
              {
                path: "/Users/me/.codex/config.toml",
                op: "modify",
                diff: [
                  { kind: "hunk", text: "@@ -1,3 +1,1 @@", old_no: null, new_no: null },
                  { kind: "context", text: 'approval_policy = "on-request"', old_no: 1, new_no: 1 },
                  { kind: "remove", text: 'model = "gpt-5-codex"', old_no: 2, new_no: null },
                  { kind: "remove", text: 'model_provider = "coffer"', old_no: 3, new_no: null },
                ],
              },
            ],
          },
        ],
      });
      api.remove.mockResolvedValue(undefined);
      renderPage();
      await heading();
      fireEvent.click(screen.getByRole("button", { name: "More actions for acme" }));
      fireEvent.click(screen.getByRole("menuitem", { name: "Delete provider" }));
      const dialog = within(await screen.findByRole("dialog"));
      expect(await dialog.findByText("Review changes · 1 file")).toBeInTheDocument();
      expect(dialog.getByText("Codex goes back to its own login")).toBeInTheDocument();
      expect(dialog.getByText("Coffer’s engine pauses")).toBeInTheDocument();
      expect(dialog.getByText('model_provider = "coffer"')).toBeInTheDocument();
      expect(api.remove).not.toHaveBeenCalled();
      fireEvent.click(dialog.getByRole("button", { name: "Delete" }));
      await waitFor(() => expect(api.remove).toHaveBeenCalledWith(UID));
    },
  );

  test("an unused provider is deleted after a confirmation, and the page returns to the list", async () => {
    serve(makeProvider());
    api.remove.mockImplementation(async () => {
      api.list.mockResolvedValue({ providers: [] });
    });
    renderPage();
    await heading();
    fireEvent.click(screen.getByRole("button", { name: "More actions for acme" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete provider" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/provider\/acme is deleted from this Mac too/)).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Delete provider" }));
    await waitFor(() => expect(api.remove).toHaveBeenCalledWith(UID));
    await waitFor(() => expect(where()).toBe("/model-providers"));
    expect(await screen.findByText("No model providers yet")).toBeInTheDocument();
  });

  test("an unknown uid says the provider was not found", async () => {
    api.list.mockResolvedValue({ providers: [makeProvider({ uid: "cn-other", name: "other" })] });
    api.get.mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));
    renderPage("/model-providers/cn-missing");
    expect(await screen.findByText("This provider no longer exists")).toBeInTheDocument();
  });
});
