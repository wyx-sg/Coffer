// pages/ProviderDetailPage.test.tsx
//
// The connection detail page: a read-only Configuration card (which NEVER
// renders a secret — only whether one is stored) and the Models card, where the
// endpoint is introspected and the curated set is written back with PATCH
// {models: [...]}. An empty set reads as "no restriction"; an endpoint that
// cannot list its models says so and leaves the current selection intact.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProviderDetailPage } from "./ProviderDetailPage";
import { ApiError } from "@/lib/api/errors";
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

// Model introspection is a network probe; drive it from the test.
const listMutate = vi.fn();
let listState: { data?: { models: string[]; message: string }; error?: unknown } = {};
vi.mock("@/lib/hooks/useModelIntrospection", () => ({
  useListProviderModels: () => ({ mutate: listMutate, isPending: false, ...listState }),
  useTestConnection: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useTestEmbedding: () => ({ mutate: vi.fn(), isPending: false, data: undefined }),
  useDetectProtocol: () => ({ mutate: vi.fn(), isPending: false }),
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

/** Resolve the fetch with these ids, as the endpoint would. */
function fetchYields(models: string[], message = "") {
  listMutate.mockImplementation(
    (
      _probe: unknown,
      opts?: { onSuccess?: (r: { models: string[]; message: string }) => void },
    ) => {
      listState = { data: { models, message } };
      opts?.onSuccess?.({ models, message });
    },
  );
}

const fetchButton = () => screen.getByRole("button", { name: /fetch models/i });

describe("ProviderDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listState = {};
    listMutate.mockImplementation(() => {});
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

  test("an empty model selection reads as unrestricted", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    renderPage();

    expect(await screen.findByText(/no restriction/i)).toBeInTheDocument();
    // Nothing curated and nothing fetched yet — the list invites a fetch.
    expect(screen.getByText(/no models yet/i)).toBeInTheDocument();
  });

  test("fetching models lists them as checkboxes and ticking one writes the selection", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    apiMock.update.mockResolvedValue(makeProvider({ models: ["gpt-5"] }));
    fetchYields(["gpt-5", "gpt-5-codex"]);
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(fetchButton());
    expect(listMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: "openai",
        base_url: "https://gw/v1",
        credential_ref: "provider/acme/key",
      }),
      expect.anything(),
    );

    const box = await screen.findByRole("checkbox", { name: "gpt-5" });
    expect(box).not.toBeChecked();
    fireEvent.click(box);

    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith("acme", { models: ["gpt-5"] });
  });

  test("unticking removes just that model; clearing writes the empty (unrestricted) set", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: ["gpt-5", "gpt-5-codex"] }));
    apiMock.update.mockResolvedValue(makeProvider({ models: ["gpt-5-codex"] }));
    renderPage();

    // The curated set renders without a fetch — it is the connection's own state.
    const box = await screen.findByRole("checkbox", { name: "gpt-5" });
    expect(box).toBeChecked();
    expect(screen.getByText(/2 model\(s\) picked/i)).toBeInTheDocument();

    fireEvent.click(box);
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(1));
    expect(apiMock.update).toHaveBeenCalledWith("acme", { models: ["gpt-5-codex"] });

    fireEvent.click(screen.getByRole("button", { name: /clear selection/i }));
    await waitFor(() => expect(apiMock.update).toHaveBeenCalledTimes(2));
    expect(apiMock.update).toHaveBeenLastCalledWith("acme", { models: [] });
  });

  test("an endpoint that cannot list models says so and leaves the selection intact", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: ["hand-typed-model"] }));
    // The probe failed (the hook is left holding the error).
    listState = { error: new ApiError("INTERNAL_ERROR", "endpoint refused") };
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    expect(screen.getByText(/could not list this endpoint's models/i)).toBeInTheDocument();
    // The curated list the user built earlier survives the failed fetch.
    expect(screen.getByRole("checkbox", { name: "hand-typed-model" })).toBeChecked();
    expect(apiMock.update).not.toHaveBeenCalled();
  });

  test("an endpoint that lists nothing surfaces the probe's message", async () => {
    apiMock.get.mockResolvedValue(makeProvider({ models: [] }));
    fetchYields([], "this endpoint does not expose a model list");
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(fetchButton());
    expect(
      await screen.findByText("this endpoint does not expose a model list"),
    ).toBeInTheDocument();
  });

  test("Edit opens the connection form with the name and protocol locked", async () => {
    apiMock.get.mockResolvedValue(makeProvider());
    renderPage();
    await screen.findByRole("heading", { name: "acme" });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const form = within(screen.getByRole("dialog"));
    expect((form.getByLabelText("Name") as HTMLInputElement).disabled).toBe(true);
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
