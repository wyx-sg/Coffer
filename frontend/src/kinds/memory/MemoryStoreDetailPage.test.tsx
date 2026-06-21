// frontend/src/kinds/memory/MemoryStoreDetailPage.test.tsx
//
// Exercises the redesigned memory store detail surface: metrics header, recall
// with a mode toggle, and the fact list → READ-ONLY preview flow (select a fact
// on the left; the right pane renders the Markdown with FileActions + delete, no
// in-app editing) plus clear-all. The `./api` module is mocked so the component
// renders without a backend.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { MemoryStoreDetailPage } from "./MemoryStoreDetailPage";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listFacts: vi.fn(),
  getMemoryStore: vi.fn(),
  getMemoryStoreMetrics: vi.fn(),
  addFact: vi.fn(),
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
  path: "/abs/memory/global/tabs-f1.md",
  folder_path: "/abs/memory/global",
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
  test("lists facts in the tree and renders the selected one", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    // The viewer renders the fact's Markdown body.
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
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

  test("a selected fact renders READ-ONLY: no Edit/Save controls", async () => {
    stubLists();
    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    expect(await screen.findByText("uses tabs over spaces")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  // Spec 007 scenario: the human-facing memory viewer is read-only and routes
  // edits to the user's own editor — it surfaces open/reveal affordances
  // (daemon-backed on web, Tauri on desktop) instead of an in-app editor.
  acceptance(
    "007-memory",
    "read-only viewer offers open/reveal affordances",
    async () => {
      stubLists();
      renderPage();
      const tree = screen.getByRole("complementary");
      fireEvent.click(await within(tree).findByText("tabs"));
      await screen.findByText("uses tabs over spaces");
      expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    },
  );

  test("deleting a selected fact calls delete after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.deleteFact).mockResolvedValue(undefined);

    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    // The viewer's Delete button opens the styled confirm dialog (no native
    // window.confirm); deletion only fires after confirming inside it.
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(api.deleteFact).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteFact).toHaveBeenCalledWith("global", "f1"));
  });

  test("does NOT delete a fact when the confirm dialog is cancelled", async () => {
    stubLists();
    vi.mocked(api.deleteFact).mockResolvedValue(undefined);

    renderPage();
    const tree = screen.getByRole("complementary");
    fireEvent.click(await within(tree).findByText("tabs"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api.deleteFact).not.toHaveBeenCalled();
  });

  test("surfaces a localized error when the facts/metrics query fails", async () => {
    vi.mocked(api.listFacts).mockRejectedValue(new ApiError("RESOURCE_NOT_FOUND", "nope"));
    vi.mocked(api.getMemoryStoreMetrics).mockRejectedValue(
      new ApiError("RESOURCE_NOT_FOUND", "nope"),
    );

    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/resource not found/i);
  });

  test("shows a load-more affordance and fetches the next page when over the page size", async () => {
    // 100 facts loaded, but the store has 150 — the cap must not silently hide
    // the rest. A "Load more" button shows the loaded/total split and, on click,
    // re-queries with a larger limit so the remaining facts become reachable.
    const page1 = Array.from({ length: 100 }, (_, i) => ({
      ...FACT,
      id: `f${i}`,
      name: `fact-${i}`,
    }));
    const page2 = Array.from({ length: 150 }, (_, i) => ({
      ...FACT,
      id: `f${i}`,
      name: `fact-${i}`,
    }));
    vi.mocked(api.listFacts).mockImplementation(async (_store, limit) =>
      (limit ?? 0) > 100 ? { facts: page2, total: 150 } : { facts: page1, total: 150 },
    );
    vi.mocked(api.getMemoryStoreMetrics).mockResolvedValue({ fact_count: 150, disk_bytes: 50 });
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

    renderPage();
    const loadMore = await screen.findByRole("button", { name: /showing 100 of 150/i });
    expect(loadMore).toBeVisible();
    expect(await screen.findByText("fact-99")).toBeVisible();

    fireEvent.click(loadMore);
    await waitFor(() => expect(api.listFacts).toHaveBeenCalledWith("global", 200, 0));
    expect(await screen.findByText("fact-149")).toBeVisible();
  });

  test("clear-all calls clearFacts after confirming in the dialog", async () => {
    stubLists();
    vi.mocked(api.clearFacts).mockResolvedValue(1);

    renderPage();
    // The header Clear-all button is disabled until metrics (fact_count) load.
    const btn = await screen.findByRole("button", { name: /clear all/i });
    await waitFor(() => expect(btn).toBeEnabled());
    fireEvent.click(btn);
    // The styled confirm dialog gates the clear; it only fires after confirming.
    const dialog = await screen.findByRole("dialog");
    expect(api.clearFacts).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: /clear all/i }));
    await waitFor(() => expect(api.clearFacts).toHaveBeenCalledWith("global"));
  });
});
