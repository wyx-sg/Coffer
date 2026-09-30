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
  is_active: false,
  internal_default: false,
  transcribe_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...over,
});
const chat = (...ids: string[]): ProviderModel[] => ids.map((id) => ({ id, modality: "text" }));
const agent = (type: "claude_code" | "codex", model: string | null): AgentOut =>
  ({
    uid: `a-${type}`,
    type,
    name: type,
    display_name: type === "codex" ? "Codex" : "Claude Code",
    model,
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
          <Route path="/model-providers/:uid" element={<ProviderDetailPage />} />
          <Route path="/model-providers/:uid/:tab" element={<ProviderDetailPage />} />
          <Route path="*" element={null} />
        </Routes>
        <Where />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const where = () => screen.getByTestId("where").textContent;
const switchFor = (id: string) => screen.getByRole("switch", { name: `Offered: ${id}` });
const typePickerFor = (id: string) => screen.getByRole("combobox", { name: `Type: ${id}` });
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

  test("a provider's used-by list is read-only", async () => {
    // Scenario (revise-web-ui-ia): "a provider's used-by list is read-only"
    agentsState.data = [agent("claude_code", "claude-opus-4-1")];
    engineState.data = { model: "gpt-5-mini", transcribe_model: null };
    serve(
      makeProvider({
        protocol: "anthropic",
        compatible_agents: ["claude_code"],
        is_active: true,
        internal_default: true,
      }),
    );
    renderPage();
    await heading();

    const usedBy = screen.getByRole("heading", { name: "Used by" }).closest("section")!;
    const claude = within(usedBy).getByRole("link", { name: /Claude Code/ });
    expect(claude).toHaveAttribute("href", "/agents/claude_code/model");
    expect(claude).toHaveTextContent("claude-opus-4-1");
    expect(claude).toHaveTextContent("Change it in Claude Code › Model");
    const engine = within(usedBy).getByRole("button", { name: /Coffer's engine/ });
    expect(engine).toHaveTextContent("gpt-5-mini");
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
    serve(makeProvider({ is_active: true, models: chat("gpt-5", "gpt-5-codex") }));
    renderPage();
    await heading();

    expect(screen.getByText("Reachable")).toBeInTheDocument();
    expect(screen.getByText("locked while Codex runs on it")).toBeInTheDocument();
    expect(screen.getByText("provider/acme")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage in Secrets" })).toHaveAttribute(
      "href",
      "/secrets",
    );
    expect(screen.getByText("2 of 3 offered")).toBeInTheDocument();
    // The Models tab carries the offered / listed count.
    expect(screen.getByRole("tab", { name: /Models/ })).toHaveTextContent("2 / 3");
    fireEvent.mouseDown(screen.getByRole("button", { name: /Choose models/ }));
    fireEvent.click(screen.getByRole("button", { name: /Choose models/ }));
    await waitFor(() => expect(where()).toBe(`/model-providers/${UID}/models`));
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
      renderPage(`/model-providers/${UID}/models`);
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
    renderPage(`/model-providers/${UID}/models`);
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
      renderPage(`/model-providers/${UID}/models`);
      await screen.findByText("text-embedding-3-large");

      // The probe's guess pre-fills each row's type.
      expect(typePickerFor("gpt-4o")).toHaveTextContent("Text / chat");
      expect(typePickerFor("text-embedding-3-large")).toHaveTextContent("Embedding");

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
    renderPage(`/model-providers/${UID}/models`);
    await screen.findByText("whisper-1");
    fireEvent.click(screen.getByRole("button", { name: "Audio" }));
    expect(screen.queryByText("gpt-5")).toBeNull();
    expect(screen.getByText("whisper-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "a failed model introspection says so and offers a retry",
    async () => {
      serve(makeProvider({ models: chat("hand-typed-model") }));
      setEndpoint({ error: new ApiError("INTERNAL_ERROR", "endpoint refused") });
      renderPage(`/model-providers/${UID}/models`);

      expect(await screen.findByText("Couldn't list this endpoint's models")).toBeInTheDocument();
      // The curated list survives the failed probe.
      expect(switchFor("hand-typed-model")).toBeChecked();
      expect(api.update).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Retry" }));
      expect(refetch).toHaveBeenCalledTimes(1);
    },
  );

  test("an endpoint that lists nothing says what that means", async () => {
    serve(makeProvider({ models: [] }));
    serves([], "the endpoint listed no models");
    renderPage(`/model-providers/${UID}/models`);
    expect(await screen.findByText("This endpoint listed no models")).toBeInTheDocument();
  });

  test("a rejected key shows in the header, a banner and Used by", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    serve(makeProvider({ is_active: true }));
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
      screen.getByText("Codex fail on every request until the key is replaced."),
    ).toBeInTheDocument();
    expect(screen.getByText("Requests fail · key rejected")).toBeInTheDocument();
    expect(screen.getByText("Rejected (401)")).toBeInTheDocument();
  });

  test("Edit renames first, then patches the endpoint; the protocol is locked while live", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    const provider = makeProvider({ is_active: true });
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

  test("Replace key tests the new key, then waits for approval when the key is in use", async () => {
    agentsState.data = [agent("codex", "gpt-5-codex")];
    serve(makeProvider({ is_active: true }));
    api.update.mockResolvedValue(makeProvider());
    listModels.mockResolvedValue({ models: chat("gpt-5"), message: "", reachable: true });
    renderPage();
    await heading();

    fireEvent.click(screen.getByRole("button", { name: "Replace key" }));
    const dialog = within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByLabelText("New key"), { target: { value: "sk-new" } });
    fireEvent.click(dialog.getByRole("button", { name: "Test" }));
    await waitFor(() =>
      expect(listModels).toHaveBeenCalledWith(
        expect.objectContaining({ secret_value: "sk-new", base_url: "https://gw/v1" }),
      ),
    );
    expect(await dialog.findByText(/The new key works — 1 model listed/)).toBeInTheDocument();

    pendingApprovals.mockResolvedValue({
      approvals: [{ id: "ap1", op: "replace_value", ref: "provider/acme", status: "pending" }],
    });
    fireEvent.click(dialog.getByRole("button", { name: "Replace key" }));
    await waitFor(() => expect(api.update).toHaveBeenCalledWith(UID, { secret_value: "sk-new" }));
    expect(await dialog.findByText("Waiting for approval in the Coffer app")).toBeInTheDocument();
    const opened = vi.fn();
    window.addEventListener("coffer:open-approvals", opened);
    fireEvent.click(dialog.getByRole("button", { name: "Review" }));
    expect(opened).toHaveBeenCalledTimes(1);
    window.removeEventListener("coffer:open-approvals", opened);
  });

  test("Delete is blocked while Coffer's engine runs on the provider", async () => {
    serve(makeProvider({ internal_default: true }));
    renderPage();
    await heading();
    fireEvent.click(screen.getByRole("button", { name: "More actions for acme" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete provider" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/acme is in use/)).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: /Coffer's engine/ })).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "Delete provider" })).toBeDisabled();
    expect(api.remove).not.toHaveBeenCalled();
  });

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
    expect(await screen.findByText("Bring your own model endpoint")).toBeInTheDocument();
  });

  test("an unknown uid says the provider was not found", async () => {
    api.list.mockResolvedValue({ providers: [makeProvider({ uid: "cn-other", name: "other" })] });
    api.get.mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));
    renderPage("/model-providers/cn-missing");
    expect(await screen.findByText("Model provider not found")).toBeInTheDocument();
  });
});
