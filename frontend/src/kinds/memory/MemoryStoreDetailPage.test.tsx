// frontend/src/kinds/memory/MemoryStoreDetailPage.test.tsx
//
// Exercises the redesigned memory store detail surface: metrics header, recall
// with a mode toggle, the add-fact form (name/description/body/type), and the
// fact list with inline edit, delete, and clear-all. The `./api` module is
// mocked so the component renders without a backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { MemoryStoreDetailPage } from "./MemoryStoreDetailPage";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listFacts: vi.fn(),
  getMemoryStore: vi.fn(),
  getMemoryStoreMetrics: vi.fn(),
  addFact: vi.fn(),
  updateFact: vi.fn(),
  deleteFact: vi.fn(),
  clearFacts: vi.fn(),
  recall: vi.fn(),
}));
const api = await import("./api");

const FACT = {
  id: "f1",
  store_name: "global",
  scope: "global" as const,
  name: "tabs",
  description: "indentation",
  text: "uses tabs over spaces",
  type: "user",
  actor: "user" as const,
  created_at: "2026-05-29T00:00:00Z",
  updated_at: "2026-05-29T00:00:00Z",
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/memory/global"]}>
        <Routes>
          <Route path="/memory/:name" element={<MemoryStoreDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubLists() {
  vi.mocked(api.listFacts).mockResolvedValue({ facts: [FACT], total: 1 });
  vi.mocked(api.getMemoryStoreMetrics).mockResolvedValue({ fact_count: 1, disk_bytes: 50 });
  vi.mocked(api.getMemoryStore).mockResolvedValue({
    ref: "memory:global",
    kind: "memory",
    name: "global",
    scope: "global",
    project_id: "0".repeat(26),
    project_root: null,
    description: null,
    config: {
      retrieval_modes: ["grep", "keyword"],
      default_mode: "keyword",
      embedding_provider: null,
      embedding_model: null,
      embedding_base_url: null,
      embedding_credential_ref: null,
      embedding_dimensions: 768,
      max_fact_chars: 8192,
    },
    enabled: true,
    created_at: "2026-05-29T00:00:00Z",
    updated_at: "2026-05-29T00:00:00Z",
  });
}

afterEach(() => vi.clearAllMocks());

describe("MemoryStoreDetailPage", () => {
  test("shows metrics and the fact list with actor + type badges", async () => {
    stubLists();
    renderPage();
    expect(await screen.findByText("tabs")).toBeInTheDocument();
    expect(screen.getByText(/1 facts/i)).toBeInTheDocument();
    expect(screen.getByText("uses tabs over spaces")).toBeInTheDocument();
  });

  test("recall passes the selected mode and renders hits", async () => {
    stubLists();
    vi.mocked(api.recall).mockResolvedValue({
      mode: "keyword",
      fallback: false,
      hits: [{ id: "f1", text: "uses tabs over spaces", score: 0.9, source: "global", time: "t" }],
    });

    renderPage();
    const input = await screen.findByPlaceholderText(/recall facts/i);
    fireEvent.change(input, { target: { value: "tabs" } });
    fireEvent.click(screen.getByRole("button", { name: /^recall$/i }));

    await waitFor(() =>
      expect(api.recall).toHaveBeenCalledWith("global", "tabs", { topK: 5, mode: "keyword" }),
    );
  });

  test("adding a fact submits name/description/body/type", async () => {
    stubLists();
    vi.mocked(api.addFact).mockResolvedValue(FACT);

    renderPage();
    // Add fact is now a dialog: click the header button to open it.
    fireEvent.click(await screen.findByRole("button", { name: /add fact/i }));
    fireEvent.change(await screen.findByLabelText(/^name/i), { target: { value: "deploy" } });
    fireEvent.change(screen.getByLabelText(/^type/i), { target: { value: "project" } });
    fireEvent.change(screen.getByLabelText(/^description/i), { target: { value: "how it ships" } });
    fireEvent.change(screen.getByLabelText(/^fact$/i), { target: { value: "make release" } });
    // The dialog's submit button (the second "Add fact" — the first opened it).
    const addButtons = screen.getAllByRole("button", { name: /add fact/i });
    fireEvent.click(addButtons[addButtons.length - 1]);

    await waitFor(() =>
      expect(api.addFact).toHaveBeenCalledWith("global", {
        text: "make release",
        name: "deploy",
        description: "how it ships",
        type: "project",
      }),
    );
  });

  test("inline editing a fact PATCHes the new text", async () => {
    stubLists();
    vi.mocked(api.updateFact).mockResolvedValue(FACT);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^edit$/i }));
    const editor = await screen.findByLabelText(/edit fact tabs/i);
    fireEvent.change(editor, { target: { value: "uses spaces now" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.updateFact).toHaveBeenCalledWith("global", "f1", { text: "uses spaces now" }),
    );
  });

  test("deleting a fact calls the delete helper after confirmation", async () => {
    stubLists();
    vi.mocked(api.deleteFact).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteFact).toHaveBeenCalledWith("global", "f1"));
    confirmSpy.mockRestore();
  });

  test("does NOT delete a fact when the confirm is cancelled", async () => {
    stubLists();
    vi.mocked(api.deleteFact).mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    expect(confirmSpy).toHaveBeenCalled();
    expect(api.deleteFact).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  test("surfaces a localized error when the facts/metrics query fails", async () => {
    vi.mocked(api.listFacts).mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));
    vi.mocked(api.getMemoryStoreMetrics).mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "nope"),
    );

    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/resource not found/i);
  });

  test("clear-all calls clearFacts after confirmation", async () => {
    stubLists();
    vi.mocked(api.clearFacts).mockResolvedValue(1);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /clear all/i }));
    await waitFor(() => expect(api.clearFacts).toHaveBeenCalledWith("global"));
    confirmSpy.mockRestore();
  });
});
