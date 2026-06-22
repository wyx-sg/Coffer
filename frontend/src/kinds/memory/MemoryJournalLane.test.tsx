// frontend/src/kinds/memory/MemoryJournalLane.test.tsx
//
// The Journal lane lists period digests (newest first); selecting a period
// renders its digest read-only. Empty store → friendly empty-state.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryJournalLane } from "./MemoryJournalLane";

vi.mock("./api", () => ({ getMemoryJournal: vi.fn() }));
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
});
