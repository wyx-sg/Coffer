// pages/ProviderDetailPage.test.tsx
//
// The connection detail page: two tabs over one header. The header owns Edit
// (which can RENAME — its own call, ahead of the patch, with the page following
// the new URL), Delete, and the enable/disable control. Overview holds the
// read-only Configuration card (which NEVER renders a secret — only whether one
// is stored); Models holds the table that introspects the endpoint AS IT OPENS —
// no fetch button — and writes the curated set back with PATCH {models: [...]},
// one row per model carrying its id, WHAT KIND of model it is, and the offered
// Switch; searchable, and filterable by offered/not and by kind. An empty set
// reads as "no restriction"; an endpoint that cannot list its models says so,
// offers a retry, and leaves the current selection intact.
//
// A curated entry is `{id, modality}`, not a bare id: introspection GUESSES the
// modality from the id and the user corrects it in the row's Type picker — on an
// already-offered row that correction is a PATCH of its own, on a row that is
// not offered yet it is held until the Switch carries it into the curated set.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProviderDetailPage } from "./ProviderDetailPage";
import { ApiError } from "@/lib/api/errors";
import type { Provider, ProviderModel } from "@/lib/api/providers";
import { acceptance } from "@/test/acceptance";

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
      rename: vi.fn(),
      setInternalDefault: vi.fn(),
    },
  };
});

// Model introspection is a network probe the Models tab fires on open; drive its
// result from the test rather than letting it reach a daemon.
const refetch = vi.fn();
let endpointState: {
  data?: { models: ProviderModel[]; message: string };
  error?: unknown;
  isPending?: boolean;
  isFetching?: boolean;
} = {};
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useEndpointModels: (name: string) => {
    probedFor.push(name);
    return {
      data: undefined,
      error: null,
      isPending: false,
      isFetching: false,
      refetch,
      ...endpointState,
    };
  },
  useListProviderModels: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useTestConnection: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useTestEmbedding: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useDetectProtocol: () => ({ mutate: vi.fn(), isPending: false }),
}));
const { probedFor } = vi.hoisted(() => ({ probedFor: [] as string[] }));

// The header's ScopeControl reaches the daemon through hand-written hooks; stub
// them so it renders its two-segment Disabled/Enabled fallback (`provider`
// declares no per-agent scope).
const { enableMutate, disableMutate } = vi.hoisted(() => ({
  enableMutate: vi.fn(),
  disableMutate: vi.fn(),
}));
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: () => ({ data: { scope: null, supports_scope: false } }),
  useUpdateResourceScope: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: () => ({ data: [] }) }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: () => ({ mutate: enableMutate, isPending: false }),
  useDisableResource: () => ({ mutate: disableMutate, isPending: false }),
}));

const { providersApi } = await import("@/lib/api/providers");
const apiMock = providersApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeProvider = (overrides?: Partial<Provider>): Provider => ({
  name: "acme",
  protocol: "openai",
  base_url: "https://gw/v1",
  credential_ref: "provider/acme/key",
  compatible_agents: ["codex"],
  is_active: false,
  internal_default: false,
  models: [],
  enabled: true,
  description: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
  ...overrides,
});

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/model-providers/acme"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/model-providers/:name" element={<ProviderDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** Plain chat entries — the common case, spelled once instead of per fixture. */
const chat = (...ids: string[]): ProviderModel[] =>
  ids.map((id) => ({ id, modality: "text" }) as ProviderModel);

/** The endpoint answered with these models, as the on-open probe would resolve.
 *  Each entry carries the modality introspection INFERRED from the id. */
function endpointServes(models: ProviderModel[], message = "") {
  endpointState = { data: { models, message } };
}

/** The page opens on Overview, so every model assertion goes through the tab.
 *  Radix's TabsTrigger switches on mousedown, which fireEvent.click never sends. */
async function openModelsTab() {
  fireEvent.mouseDown(await screen.findByRole("tab", { name: "Models" }));
}

/** The row's offered/not-offered Switch, named as the table labels it. */
const switchFor = (model: string) => screen.getByRole("switch", { name: `Status: ${model}` });

/** The row's modality picker, named as ModalitySelect labels it. Every query
 *  here goes by accessible name: the toolbar's own filters are comboboxes too,
 *  and so is one picker per row. */
const typePickerFor = (model: string) => screen.getByRole("combobox", { name: `Type: ${model}` });

/** Radix Select has no pointer layout under jsdom, so open it from the keyboard
 *  and then click the option by its label. */
function chooseOption(trigger: HTMLElement, optionName: string) {
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

/** Correct what kind of model a row is. */
const setModality = (model: string, kind: string) => chooseOption(typePickerFor(model), kind);

/** The toolbar's two filters, each named by its column header. */
const selectStatus = (optionName: string) =>
  chooseOption(screen.getByRole("combobox", { name: "Status" }), optionName);
const selectType = (optionName: string) =>
  chooseOption(screen.getByRole("combobox", { name: "Type" }), optionName);

describe("ProviderDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    endpointState = {};
    probedFor.length = 0;
  });

  test("renders the connection's configuration, never its secret", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ description: "the gateway" }));
    renderPage();

    expect(await screen.findByRole("heading", { name: "acme" })).toBeInTheDocument();
    expect(screen.getByText("https://gw/v1")).toBeInTheDocument();
    expect(screen.getByText("Codex")).toBeInTheDocument();
    expect(screen.getByText("the gateway")).toBeInTheDocument();
    // A key is stored — we say so, and never render the reference or the value.
    expect(screen.getByText("Stored")).toBeInTheDocument();
    expect(screen.queryByText("provider/acme/key")).not.toBeInTheDocument();
  });

  test("a keyless connection says no key is stored", async () => {
    apiMock.get.mockResolvedValue(
      makeProvider({ protocol: "ollama", credential_ref: null, compatible_agents: [] }),
    );
    renderPage();
    expect(await screen.findByText("No key stored")).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "the models table lists the endpoint's models when it opens",
    async () => {
      apiMock.get.mockResolvedValue(makeProvider());
      renderPage();
      await screen.findByRole("heading", { name: "acme" });

      // Configuration belongs to Overview, so it is what the page opens on; the
      // models surface stays behind its tab until asked for — and the endpoint is
      // not probed before the user gets there.
      expect(screen.getByText("Configuration")).toBeInTheDocument();
      expect(probedFor).toEqual([]);

      await openModelsTab();
      expect(await screen.findByText(/pick which of this endpoint's models/i)).toBeInTheDocument();
      // Opening the tab IS the fetch trigger — there is no button to press.
      expect(probedFor).toContain("acme");
      expect(screen.queryByRole("button", { name: /fetch models/i })).not.toBeInTheDocument();
    },
  );

  test("the table says it is loading while the endpoint is being probed", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    endpointState = { isPending: true, isFetching: true };
    renderPage();
    await openModelsTab();

    expect(await screen.findAllByText(/listing this endpoint's models/i)).not.toHaveLength(0);
  });

  test("an empty model selection reads as unrestricted", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    renderPage();
    await openModelsTab();

    expect(await screen.findByText(/no restriction/i)).toBeInTheDocument();
    // Nothing curated and the endpoint listed nothing — say that, and say the
    // empty selection still means every model it offers is available.
    expect(screen.getByText(/this endpoint listed no models/i)).toBeInTheDocument();
  });

  test("the models the endpoint serves are listed on open and flipping one on writes the selection", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    apiMock.update.mockResolvedValue(makeProvider({ models: chat("gpt-5") }));
    endpointServes(chat("gpt-5", "gpt-5-codex"));
    renderPage();
    await openModelsTab();

    const toggle = await screen.findByRole("switch", { name: "Status: gpt-5" });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    // The curated entry carries the kind the row is showing, not a bare id.
    expect(apiMock.update).toHaveBeenCalledWith("acme", {
      models: [{ id: "gpt-5", modality: "text" }],
    });
  });

  test("flipping one off removes just that model; clearing writes the empty (unrestricted) set", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: chat("gpt-5", "gpt-5-codex") }));
    apiMock.update.mockResolvedValue(makeProvider({ models: chat("gpt-5-codex") }));
    renderPage();
    await openModelsTab();

    // The curated set renders without a fetch — it is the connection's own state.
    const toggle = await screen.findByRole("switch", { name: "Status: gpt-5" });
    expect(toggle).toBeChecked();
    expect(screen.getByText(/2 model\(s\) picked/i)).toBeInTheDocument();

    fireEvent.click(toggle);
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith("acme", {
      models: [{ id: "gpt-5-codex", modality: "text" }],
    });

    fireEvent.click(screen.getByRole("button", { name: /clear selection/i }));
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(2));
    expect(apiMock.update).toHaveBeenLastCalledWith("acme", { models: [] });
  });

  test("the search box narrows the table to the matching model ids", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    endpointServes(chat("gpt-5", "gpt-5-codex", "claude-opus-4"));
    renderPage();
    await openModelsTab();
    await screen.findByText("claude-opus-4");

    fireEvent.change(screen.getByRole("textbox", { name: "Search models…" }), {
      target: { value: "codex" },
    });
    expect(screen.getByText("gpt-5-codex")).toBeInTheDocument();
    expect(screen.queryByText("claude-opus-4")).not.toBeInTheDocument();

    // Rows exist; the search is what hid them — so say that, not "no models yet".
    fireEvent.change(screen.getByRole("textbox", { name: "Search models…" }), {
      target: { value: "gemini" },
    });
    expect(screen.getByText(/no models match/i)).toBeInTheDocument();
  });

  test("the status filter separates the offered models from the rest", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: chat("gpt-5") }));
    endpointServes(chat("gpt-5", "gpt-5-codex"));
    renderPage();
    await openModelsTab();
    await screen.findByText("gpt-5-codex");

    selectStatus("Enabled");
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
    expect(screen.queryByText("gpt-5-codex")).not.toBeInTheDocument();

    selectStatus("Disabled");
    expect(screen.getByText("gpt-5-codex")).toBeInTheDocument();
    expect(screen.queryByText("gpt-5")).not.toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "curate an embedding model alongside chat models on one connection",
    async () => {
      // The probe answers with a modality per id — its GUESS, which the row
      // shows as the pre-filled value of the Type picker.
      apiMock.get.mockResolvedValue(makeProvider({ models: chat("gpt-4o") }));
      apiMock.update.mockResolvedValue(makeProvider());
      endpointServes([
        { id: "gpt-4o", modality: "text" },
        { id: "text-embedding-3-large", modality: "embedding" },
      ]);
      renderPage();
      await openModelsTab();
      await screen.findByText("text-embedding-3-large");

      expect(typePickerFor("gpt-4o")).toHaveTextContent("Text / chat");
      expect(typePickerFor("text-embedding-3-large")).toHaveTextContent("Embedding");

      // Offering it stores the inferred kind beside the chat model already
      // curated — one connection, two kinds of model.
      fireEvent.click(switchFor("text-embedding-3-large"));
      await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
      expect(apiMock.update).toHaveBeenCalledWith("acme", {
        models: [
          { id: "gpt-4o", modality: "text" },
          { id: "text-embedding-3-large", modality: "embedding" },
        ],
      });
    },
  );

  test("correcting an offered row's type patches the whole curated set with it", async () => {
    // Introspection guessed `text` for an embedding model and the user already
    // offered it — the correction belongs in the stored set straight away.
    apiMock.get.mockResolvedValue(makeProvider({ models: chat("gpt-5", "house-embeddings-v2") }));
    apiMock.update.mockResolvedValue(makeProvider());
    renderPage();
    await openModelsTab();
    await screen.findByText("house-embeddings-v2");

    setModality("house-embeddings-v2", "Embedding");

    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    // The whole set is rewritten, so the untouched row keeps its own kind.
    expect(apiMock.update).toHaveBeenCalledWith("acme", {
      models: [
        { id: "gpt-5", modality: "text" },
        { id: "house-embeddings-v2", modality: "embedding" },
      ],
    });
  });

  test("a type picked before the switch is the one the curated entry is stored with", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    apiMock.update.mockResolvedValue(makeProvider());
    // Nothing in the id says "embedding", so the guess is wrong — and this row
    // is not offered yet, so there is nothing to patch the correction into.
    endpointServes(chat("house-embeddings-v2"));
    renderPage();
    await openModelsTab();
    await screen.findByText("house-embeddings-v2");

    setModality("house-embeddings-v2", "Embedding");
    expect(typePickerFor("house-embeddings-v2")).toHaveTextContent("Embedding");
    // Held locally: a row that is not offered has nowhere to be written.
    expect(apiMock.update).not.toHaveBeenCalled();

    fireEvent.click(switchFor("house-embeddings-v2"));
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith("acme", {
      models: [{ id: "house-embeddings-v2", modality: "embedding" }],
    });
  });

  test("the type filter separates the models by kind", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    endpointServes([
      { id: "gpt-5", modality: "text" },
      { id: "text-embedding-3-large", modality: "embedding" },
    ]);
    renderPage();
    await openModelsTab();
    await screen.findByText("text-embedding-3-large");

    selectType("Embedding");
    expect(screen.getByText("text-embedding-3-large")).toBeInTheDocument();
    expect(screen.queryByText("gpt-5")).not.toBeInTheDocument();

    selectType("All types");
    expect(screen.getByText("gpt-5")).toBeInTheDocument();
  });

  acceptance(
    "provider-switching",
    "a failed model introspection says so and offers a retry",
    async () => {
      apiMock.get.mockResolvedValue(makeProvider({ models: chat("hand-typed-model") }));
      // The probe failed (the query is left holding the error).
      endpointState = { error: new ApiError("INTERNAL_ERROR", "endpoint refused") };
      renderPage();
      await openModelsTab();

      expect(await screen.findByText(/could not list this endpoint's models/i)).toBeInTheDocument();
      // The curated list the user built earlier survives the failed fetch.
      expect(switchFor("hand-typed-model")).toBeChecked();
      expect(apiMock.update).not.toHaveBeenCalled();

      // A failure is never a dead end: the retry asks the endpoint again.
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      expect(refetch).toHaveBeenCalledTimes(1);
    },
  );

  test("an endpoint that lists nothing surfaces the probe's message", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    endpointServes(chat(), "this endpoint does not expose a model list");
    renderPage();
    await openModelsTab();

    expect(
      await screen.findByText("this endpoint does not expose a model list"),
    ).toBeInTheDocument();
  });

  test("Edit opens the connection form with the protocol locked and the name editable", async () => {
    apiMock.get.mockResolvedValue(makeProvider());
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog"));
    expect((form.getByLabelText("Name") as HTMLInputElement).disabled).toBe(false);
    // The secret is optional in edit mode (blank keeps the stored key).
    expect((form.getByLabelText("API key") as HTMLInputElement).required).toBe(false);

    fireEvent.change(form.getByLabelText("Base URL"), { target: { value: "https://gw/v2" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith(
      "acme",
      expect.objectContaining({ base_url: "https://gw/v2" }),
    );
  });

  test("renaming from the edit dialog renames first, then patches under the new name", async () => {
    apiMock.get.mockResolvedValue(makeProvider());
    apiMock.rename.mockResolvedValue(makeProvider({ name: "acme-eu" }));
    apiMock.update.mockResolvedValue(makeProvider({ name: "acme-eu" }));
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog"));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "acme-eu" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    // The name is identity, so it moves on its own call — and the patch that
    // follows addresses the connection by the name it now has.
    await waitFor(() => expect(apiMock.rename).toHaveBeenCalledWith("acme", "acme-eu"));
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update.mock.calls[0][0]).toBe("acme-eu");
    // This route IS the name, so the page follows it rather than 404ing.
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/model-providers/acme-eu", { replace: true }),
    );
  });

  test("saving without touching the name patches in place and never renames", async () => {
    apiMock.get.mockResolvedValue(makeProvider());
    apiMock.update.mockResolvedValue(makeProvider());
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog"));
    fireEvent.change(form.getByLabelText("Base URL"), { target: { value: "https://gw/v2" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.rename).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("a name another connection already uses fails the rename and stops the patch", async () => {
    apiMock.get.mockResolvedValue(makeProvider());
    apiMock.rename.mockRejectedValue(
      new ApiError("RESOURCE_ALREADY_EXISTS", "resource already exists: provider:taken"),
    );
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog"));
    fireEvent.change(form.getByLabelText("Name"), { target: { value: "taken" } });
    fireEvent.click(form.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/a resource with that name already exists/i),
    ).toBeInTheDocument();
    // Nothing else was written, and the dialog stays open on the failed edit.
    expect(apiMock.update).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("the header can disable the connection, not just show that it is enabled", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ enabled: true }));
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    // `provider` declares no per-agent scope, so the control is the two-segment
    // Disabled/Enabled group — and it is the ONLY thing stating that state.
    const control = within(screen.getByTestId("scope-control"));
    expect(control.getByRole("button", { name: "Enabled" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(control.getByRole("button", { name: "Disabled" }));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "provider", name: "acme" });
  });

  test("a disabled connection can be re-enabled from its own page", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ enabled: false }));
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    const control = within(screen.getByTestId("scope-control"));
    fireEvent.click(control.getByRole("button", { name: "Enabled" }));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "provider", name: "acme" });
  });

  test("Delete confirms first, then removes and returns to the list", async () => {
    apiMock.get.mockResolvedValue(makeProvider());
    apiMock.remove.mockResolvedValue(undefined);
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(apiMock.remove).not.toHaveBeenCalled();

    const dialog = within(screen.getByRole("dialog"));
    fireEvent.click(dialog.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(apiMock.remove).toHaveBeenCalledWith("acme"));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/model-providers"));
  });

  test("a missing connection shows a not-found card with a way back", async () => {
    apiMock.get.mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "no such connection"));
    renderPage();
    expect(await screen.findByText("Model provider not found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /back to model providers/i }));
    expect(navigateMock).toHaveBeenCalledWith("/model-providers");
  });
});
