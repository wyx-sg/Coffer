// frontend/src/kinds/memory/MemoryChangelogLane.test.tsx
//
// The Changelog lane is the consolidation log, shown through the shared
// file-tree lane as one file row: select it to preview the Markdown read-only;
// an absent log shows a friendly empty-state. The preview offers open/reveal
// (the log has a path) plus a delete action with a confirm dialog wired to the
// consolidation-log DELETE helper.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryChangelogLane } from "./MemoryChangelogLane";

vi.mock("./api", () => ({
  getMemoryConsolidationLog: vi.fn(),
  deleteConsolidationLog: vi.fn(),
}));
const api = await import("./api");

function renderLane() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryChangelogLane store="global" />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MemoryChangelogLane", () => {
  test("renders the consolidation log Markdown when a row is selected", async () => {
    vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
      text: "merged 3 facts",
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    renderLane();
    fireEvent.click(await screen.findByRole("button", { name: /^Changelog$/ }));
    expect(await screen.findByText("merged 3 facts")).toBeInTheDocument();
  });

  test("shows the empty-state when the log is absent", async () => {
    vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
      text: null,
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    renderLane();
    expect(await screen.findByText(/no changelog yet/i)).toBeInTheDocument();
  });

  test("preview shows the three-button toolbar (open / reveal / delete)", async () => {
    vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
      text: "merged 3 facts",
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    renderLane();
    fireEvent.click(await screen.findByRole("button", { name: /^Changelog$/ }));
    expect(await screen.findByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  test("delete asks for confirmation then calls the log DELETE helper", async () => {
    vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
      text: "merged 3 facts",
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    vi.mocked(api.deleteConsolidationLog).mockResolvedValue();
    renderLane();
    fireEvent.click(await screen.findByRole("button", { name: /^Changelog$/ }));
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteConsolidationLog).toHaveBeenCalledWith("global"));
  });
});
