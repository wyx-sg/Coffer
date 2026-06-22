// frontend/src/kinds/memory/MemoryJournalLane.test.tsx
//
// The Journal lane lists period digests (newest first); selecting a period
// renders its digest read-only. Empty store → friendly empty-state.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryJournalLane } from "./MemoryJournalLane";

vi.mock("./api", () => ({ getMemoryJournal: vi.fn(), deleteJournalPeriod: vi.fn() }));
const api = await import("./api");

function renderLane() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryJournalLane store="global" />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MemoryJournalLane", () => {
  test("lists periods and renders the selected digest", async () => {
    vi.mocked(api.getMemoryJournal).mockResolvedValue({
      files: [
        { period: "2026-06", text: "june digest", path: "/p/2026-06.md", folder_path: "/p" },
        { period: "2026-05", text: "may digest", path: "/p/2026-05.md", folder_path: "/p" },
      ],
    });
    renderLane();
    fireEvent.click(await screen.findByText("2026-06"));
    expect(await screen.findByText("june digest")).toBeInTheDocument();
  });

  test("shows the empty-state when there are no journal files", async () => {
    vi.mocked(api.getMemoryJournal).mockResolvedValue({ files: [] });
    renderLane();
    expect(await screen.findByText(/no journal entries yet/i)).toBeInTheDocument();
  });

  test("preview shows the three-button toolbar (open / reveal / delete)", async () => {
    vi.mocked(api.getMemoryJournal).mockResolvedValue({
      files: [{ period: "2026-06", text: "june digest", path: "/p/2026-06.md", folder_path: "/p" }],
    });
    renderLane();
    fireEvent.click(await screen.findByText("2026-06"));
    expect(await screen.findByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  test("delete asks for confirmation then calls deleteJournalPeriod", async () => {
    vi.mocked(api.getMemoryJournal).mockResolvedValue({
      files: [{ period: "2026-06", text: "june digest", path: "/p/2026-06.md", folder_path: "/p" }],
    });
    vi.mocked(api.deleteJournalPeriod).mockResolvedValue();
    renderLane();
    fireEvent.click(await screen.findByText("2026-06"));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteJournalPeriod).toHaveBeenCalledWith("global", "2026-06"));
  });
});
