// pages/settings/ModelsPage.test.tsx
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor, fireEvent, act, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ModelsPage } from "./ModelsPage";
import type { Model } from "@/lib/api/models";

vi.mock("@/lib/api/models", () => ({
  modelsApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}));

// The page now also renders the embedding/chunking config below the model
// list, which reads its config through this hook — mock the network boundary.
vi.mock("@/lib/hooks/useEmbeddingConfig", () => ({
  useEmbeddingConfig: vi.fn(() => ({
    data: {
      enabled: false,
      provider: "local",
      model: "",
      base_url: null,
      credential_ref: null,
      dimensions: 768,
      default_chunk_size: 512,
      default_chunk_overlap: 64,
      updated_at: null,
    },
    isPending: false,
    error: null,
  })),
  useUpdateEmbeddingConfig: vi.fn(() => ({ mutate: vi.fn(), isPending: false, error: null })),
}));

const { modelsApi } = await import("@/lib/api/models");
const modelsApiMock = modelsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const makeModel = (overrides?: Partial<Model>): Model => ({
  id: "model-1",
  display_name: "Claude Sonnet",
  provider: "anthropic",
  model: "claude-3-5-sonnet-20241022",
  is_default: true,
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
        <ModelsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ModelsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("shows loading state initially", () => {
    modelsApiMock.list.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  test("shows empty state when no models", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no models configured yet/i)).toBeInTheDocument(),
    );
  });

  test("renders model list", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Claude Sonnet")).toBeInTheDocument(),
    );
    expect(screen.getByText(/anthropic/i)).toBeInTheDocument();
  });

  test("renders the embedding/chunking section below the model list", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Claude Sonnet")).toBeInTheDocument(),
    );
    // The merged embedding config card renders on the same page, with its
    // enable toggle.
    expect(screen.getByText("Embedding")).toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  test("a single delete click does NOT delete — it opens a confirm dialog first", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    modelsApiMock.remove.mockResolvedValue(undefined);
    renderPage();

    await waitFor(() => expect(screen.getByText("Claude Sonnet")).toBeInTheDocument());

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    });

    // The confirm dialog is shown and nothing has been deleted yet.
    await waitFor(() => expect(screen.getByText("Delete model?")).toBeInTheDocument());
    expect(modelsApiMock.remove).not.toHaveBeenCalled();
  });

  test("confirming the dialog deletes the model", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [makeModel()] });
    modelsApiMock.remove.mockResolvedValue(undefined);
    renderPage();

    await waitFor(() => expect(screen.getByText("Claude Sonnet")).toBeInTheDocument());

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    });
    await waitFor(() => screen.getByText("Delete model?"));

    const dialog = screen.getByRole("dialog");
    const confirmBtn = within(dialog).getByRole("button", { name: /^delete$/i });
    act(() => {
      fireEvent.click(confirmBtn);
    });

    await waitFor(() => expect(modelsApiMock.remove).toHaveBeenCalledWith("model-1"));
  });

  test("opens add model dialog on Add model click", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage();
    const addBtn = await screen.findByRole("button", { name: /add model/i });
    act(() => {
      fireEvent.click(addBtn);
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Display name")).toBeInTheDocument(),
    );
  });
});

describe("ModelForm validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("shows validation error when required fields are empty", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [] });
    renderPage();

    const addBtn = await screen.findByRole("button", { name: /add model/i });
    act(() => {
      fireEvent.click(addBtn);
    });

    // Wait for dialog to open
    await waitFor(() => screen.getByLabelText("Display name"));

    // Submit without filling in anything
    const saveBtn = screen.getByRole("button", { name: /^save$/i });
    act(() => {
      fireEvent.click(saveBtn);
    });

    await waitFor(() =>
      expect(screen.getAllByText("required").length).toBeGreaterThan(0),
    );
  });

  test("submits with valid values", async () => {
    modelsApiMock.list.mockResolvedValue({ models: [] });
    modelsApiMock.create.mockResolvedValue(makeModel());
    renderPage();

    const addBtn = await screen.findByRole("button", { name: /add model/i });
    act(() => {
      fireEvent.click(addBtn);
    });

    await waitFor(() => screen.getByLabelText("Display name"));

    act(() => {
      fireEvent.change(screen.getByLabelText("Display name"), {
        target: { value: "My Model" },
      });
      fireEvent.change(screen.getByLabelText("Model ID"), {
        target: { value: "claude-3-5-sonnet" },
      });
      fireEvent.change(screen.getByLabelText("Credential reference"), {
        target: { value: "ANTHROPIC_API_KEY" },
      });
    });

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    });

    await waitFor(() => expect(modelsApiMock.create).toHaveBeenCalled());
  });
});
