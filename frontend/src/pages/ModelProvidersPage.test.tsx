// pages/ModelProvidersPage.test.tsx
//
// The connection library is now a DataTable like every other list surface:
// search + filters + selection + pagination, the per-row reach control (one
// button stating the reach, over a panel of choices), a bulk bar carrying that
// same control plus delete, and a row click that opens the connection's detail
// page (where editing and the model curation live — no per-row pencil).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { acceptance } from "@/test/acceptance";
import { ModelProvidersPage } from "./ModelProvidersPage";
import type { Provider } from "@/lib/api/providers";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/lib/api/providers", async (orig) => {
  const actual = await orig<typeof import("@/lib/api/providers")>();
  return {
    ...actual,
    providersApi: {
      list: vi.fn(),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
      activate: vi.fn(),
      setInternalDefault: vi.fn(),
    },
  };
});

// The row reach control + the bulk bar go through the kind-agnostic resource
// endpoints and the scope sub-route; stub both so no request leaves the test.
vi.mock("@/lib/api/resources", () => ({
  resourcesApi: { enable: vi.fn(), disable: vi.fn(), remove: vi.fn() },
}));
vi.mock("@/lib/api/scope", () => ({
  scopeApi: { get: vi.fn(), put: vi.fn() },
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "cc" }] })),
}));

// The dialog's introspection (detect / test / fetch) hits the network; stub the
// hooks. `detect` synchronously resolves to a protocol so the create flow works.
let detectResult = "openai";
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useDetectProtocol: () => ({
    isPending: false,
    mutate: (_p: unknown, o?: { onSuccess?: (r: { protocol: string }) => void }) =>
      o?.onSuccess?.({ protocol: detectResult }),
  }),
  useListProviderModels: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
  useTestConnection: () => ({ isPending: false, mutate: vi.fn(), data: undefined }),
}));

const { providersApi } = await import("@/lib/api/providers");
const { resourcesApi } = await import("@/lib/api/resources");
const { scopeApi } = await import("@/lib/api/scope");
const apiMock = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const resourceMock = resourcesApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const scopeMock = scopeApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeProvider = (overrides?: Partial<Provider>): Provider => ({
  name: "acme",
  protocol: "anthropic",
  base_url: "https://gw/anthropic",
  credential_ref: "provider/acme/key",
  compatible_agents: ["claude_code"],
  is_active: false,
  internal_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ModelProvidersPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** The <tr> carrying the named connection. */
const rowFor = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

/** Pick an option in one of the toolbar's filter dropdowns. */
function selectFilter(filterLabel: string, optionName: string) {
  fireEvent.click(screen.getByRole("combobox", { name: filterLabel }));
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

describe("ModelProvidersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    detectResult = "openai";
    resourceMock.enable.mockResolvedValue(undefined);
    resourceMock.disable.mockResolvedValue(undefined);
    scopeMock.put.mockResolvedValue(undefined);
    scopeMock.get.mockResolvedValue({ scope: null, supports_scope: true });
  });

  acceptance(
    "provider-switching",
    "the connections page lists profiles and their compatible agents",
    async () => {
      apiMock.list.mockResolvedValue({
        providers: [
          makeProvider({ name: "official", is_active: true, compatible_agents: ["claude_code"] }),
          makeProvider({ name: "agnes", protocol: "openai", compatible_agents: ["codex"] }),
        ],
      });

      renderPage();

      // lists the connections with their compatible-agent chips
      expect(await screen.findByText("official")).toBeInTheDocument();
      expect(screen.getByText("agnes")).toBeInTheDocument();
      expect(screen.getByText("Claude Code")).toBeInTheDocument();
      expect(screen.getByText("Codex")).toBeInTheDocument();
      // …and their endpoints, in the base_url column.
      expect(screen.getAllByText("https://gw/anthropic").length).toBeGreaterThan(0);

      // No per-row "Switch" — activation is per-agent, on the Agent Overview tab.
      expect(screen.queryByRole("button", { name: "Switch" })).not.toBeInTheDocument();
      expect(apiMock.activate).not.toHaveBeenCalled();
    },
  );

  test("create with the Custom provider picks the protocol by hand", async () => {
    apiMock.list.mockResolvedValue({ providers: [] });
    apiMock.create.mockResolvedValue(makeProvider({ name: "myconn", protocol: "openai" }));

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Add model provider/i }));
    // Scope to the dialog: the table toolbar carries a "Vendor" filter with the
    // same label as the form's preset picker.
    const form = within(screen.getByRole("dialog"));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "myconn" } });
    // Pick the "Custom" provider → a protocol picker appears.
    fireEvent.change(form.getByLabelText("Vendor"), { target: { value: "custom" } });
    fireEvent.change(form.getByLabelText("Protocol"), { target: { value: "openai" } });
    fireEvent.change(form.getByLabelText("Base URL"), { target: { value: "https://gw/v1" } });
    fireEvent.change(form.getByLabelText("API key"), { target: { value: "sk-x" } });
    // No agent checkboxes here: the dialog does not decide reach.
    expect(form.queryAllByRole("checkbox")).toHaveLength(0);
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiMock.create).toHaveBeenCalledTimes(1));
    expect(apiMock.create.mock.calls[0][0]).toMatchObject({
      name: "myconn",
      protocol: "openai",
      secret_value: "sk-x",
    });
    // The form carries NO compatible-agents field: that key is gone from
    // ProviderCreate (reach is the resource's per-agent scope, pre-filled from
    // the wire server-side). Pydantic ignores unknown fields, so sending it
    // would 200 and silently drop the user's choice — assert on the body.
    expect(apiMock.create.mock.calls[0][0]).not.toHaveProperty("compatible_agents");
  });

  acceptance("provider-switching", "create an ollama connection without a credential", async () => {
    apiMock.list.mockResolvedValue({ providers: [] });
    apiMock.create.mockResolvedValue(
      makeProvider({
        name: "local-llm",
        protocol: "ollama",
        credential_ref: null,
        internal_default: false,
      }),
    );

    renderPage();
    // open the add dialog
    fireEvent.click(await screen.findByRole("button", { name: /Add model provider/i }));

    // Scope to the dialog — the toolbar's vendor filter shares the "Vendor" label.
    const form = within(screen.getByRole("dialog"));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "local-llm" } });
    // The Ollama preset fills the protocol + endpoint and is keyless.
    fireEvent.change(form.getByLabelText("Vendor"), { target: { value: "ollama" } });
    expect(form.queryByLabelText("API key")).not.toBeInTheDocument();

    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiMock.create).toHaveBeenCalledTimes(1));
    const body = apiMock.create.mock.calls[0][0];
    expect(body).toMatchObject({
      name: "local-llm",
      protocol: "ollama",
      base_url: "http://localhost:11434",
    });
    // NEITHER secret_value nor credential_ref is sent for ollama.
    expect(body.secret_value).toBeUndefined();
    expect(body.credential_ref).toBeUndefined();
  });

  test("holds only the connection library — no engine or embedding card", async () => {
    // Coffer's own engine + embedding config moved to Settings → Engine: they
    // configure Coffer itself, not a resource served to agents.
    apiMock.list.mockResolvedValue({ providers: [makeProvider({ name: "acme" })] });
    renderPage();
    await screen.findByText("acme");
    expect(screen.queryByText("Internal engine")).not.toBeInTheDocument();
    expect(screen.queryByText("Embedding")).not.toBeInTheDocument();
  });

  test("the row carries no edit action — editing lives on the detail page", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider({ name: "acme" })] });
    renderPage();
    await screen.findByText("acme");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  test("search narrows the rows over name, endpoint and description", async () => {
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({ name: "official" }),
        makeProvider({ name: "agnes", base_url: "https://apihub.agnes-ai.com/v1" }),
      ],
    });
    renderPage();
    await screen.findByText("official");

    const search = screen.getByRole("textbox");
    fireEvent.change(search, { target: { value: "apihub" } });
    expect(screen.getByText("agnes")).toBeInTheDocument();
    expect(screen.queryByText("official")).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "offic" } });
    expect(screen.getByText("official")).toBeInTheDocument();
    expect(screen.queryByText("agnes")).not.toBeInTheDocument();
  });

  test("the vendor and status filters narrow the rows", async () => {
    apiMock.list.mockResolvedValue({
      providers: [
        // A private gateway is no vendor's own endpoint → Custom; only the second
        // row sits on OpenAI's, so filtering by vendor has to split the two.
        makeProvider({ name: "official", base_url: "https://gw/anthropic", enabled: true }),
        makeProvider({
          name: "agnes",
          protocol: "openai",
          base_url: "https://api.openai.com/v1",
          enabled: false,
        }),
      ],
    });
    renderPage();
    await screen.findByText("official");

    selectFilter("Vendor", "OpenAI");
    expect(screen.getByText("agnes")).toBeInTheDocument();
    expect(screen.queryByText("official")).not.toBeInTheDocument();

    selectFilter("Vendor", "All vendors");
    // The status filter tracks the status COLUMN, which is reach now: an
    // enabled connection with no scope reads as "Every agent".
    selectFilter("Status", "Every agent");
    expect(screen.getByText("official")).toBeInTheDocument();
    expect(screen.queryByText("agnes")).not.toBeInTheDocument();
  });

  test("the vendor column falls back to Custom for an unrecognised endpoint", async () => {
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({ name: "agnes", base_url: "https://apihub.agnes-ai.com/v1" }),
        // A trailing slash and upper case are cosmetic — still OpenAI's endpoint.
        makeProvider({ name: "official", base_url: "https://API.openai.com/v1/" }),
      ],
    });
    renderPage();
    await screen.findByText("agnes");

    expect(within(rowFor("agnes")).getByText("Custom")).toBeInTheDocument();
    expect(within(rowFor("official")).getByText("OpenAI")).toBeInTheDocument();
  });

  test("the status cell is the reach control, and it does not navigate", async () => {
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({ name: "official", enabled: true }),
        makeProvider({ name: "agnes", enabled: false }),
      ],
    });
    renderPage();
    await screen.findByText("official");

    // A Switch could not say "offer this endpoint to exactly these agents".
    expect(screen.queryByRole("switch")).toBeNull();
    // One button per row, and its label IS that row's reach.
    const reachIn = (name: string) =>
      within(within(rowFor(name)).getByTestId("scope-control")).getByRole("button");
    expect(reachIn("official")).toHaveTextContent(/every agent/i);
    expect(reachIn("agnes")).toHaveTextContent(/^disabled/i);

    fireEvent.click(reachIn("official"));
    fireEvent.click(screen.getByRole("radio", { name: /^disabled$/i }));
    await waitFor(() => expect(resourceMock.disable).toHaveBeenCalledWith("provider", "official"));
    fireEvent.click(reachIn("agnes"));
    fireEvent.click(screen.getByRole("radio", { name: /every agent/i }));
    await waitFor(() => expect(resourceMock.enable).toHaveBeenCalledWith("provider", "agnes"));
    // The control must not fall through to the row's navigation.
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("clicking a row opens the connection detail page", async () => {
    apiMock.list.mockResolvedValue({ providers: [makeProvider({ name: "acme" })] });
    renderPage();
    await screen.findByText("acme");

    fireEvent.click(screen.getByText("https://gw/anthropic"));
    expect(navigateMock).toHaveBeenCalledWith("/model-providers/acme");
  });

  test("the bulk reach control fans the chosen state out over the selection", async () => {
    apiMock.list.mockResolvedValue({
      providers: [
        makeProvider({ name: "official", enabled: false }),
        makeProvider({ name: "agnes", enabled: false }),
      ],
    });
    renderPage();
    await screen.findByText("official");

    // The head checkbox selects the whole page.
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    // A mixed selection has no current reach, so the bar's button names the
    // action instead of a state.
    const bar = () => within(screen.getByTestId("bulk-reach-control")).getByRole("button");
    expect(bar()).toHaveTextContent(/set reach/i);
    // "Every agent" is enable + an unscoped write, per selected row.
    fireEvent.click(bar());
    fireEvent.click(screen.getByRole("radio", { name: /every agent/i }));
    await waitFor(() => expect(resourceMock.enable).toHaveBeenCalledTimes(2));
    expect(resourceMock.enable.mock.calls.map((c) => c[1]).sort()).toEqual(["agnes", "official"]);
    await waitFor(() => expect(scopeMock.put).toHaveBeenCalledTimes(2));
    expect(scopeMock.put.mock.calls.every((c) => c[2] === null)).toBe(true);

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(bar());
    fireEvent.click(screen.getByRole("radio", { name: /^disabled$/i }));
    await waitFor(() => expect(resourceMock.disable).toHaveBeenCalledTimes(2));
  });

  test("bulk delete confirms first, then removes every selected connection", async () => {
    apiMock.list.mockResolvedValue({
      providers: [makeProvider({ name: "official" }), makeProvider({ name: "agnes" })],
    });
    apiMock.remove.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("official");

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    // Styled confirm — nothing is removed until it is confirmed.
    const dialog = screen.getByRole("dialog");
    expect(apiMock.remove).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(apiMock.remove).toHaveBeenCalledTimes(2));
    expect(apiMock.remove.mock.calls.map((c) => c[0]).sort()).toEqual(["agnes", "official"]);
  });

  test("the per-row delete action confirms then removes that one connection", async () => {
    apiMock.list.mockResolvedValue({
      providers: [makeProvider({ name: "official" }), makeProvider({ name: "agnes" })],
    });
    apiMock.remove.mockResolvedValue(undefined);
    renderPage();
    await screen.findByText("official");

    fireEvent.click(screen.getByRole("button", { name: "Delete: agnes" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(apiMock.remove).toHaveBeenCalledTimes(1));
    expect(apiMock.remove).toHaveBeenCalledWith("agnes");
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
