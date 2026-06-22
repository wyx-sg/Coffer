// frontend/src/kinds/memory/MemoryChangelogLane.test.tsx
//
// The Changelog lane renders the consolidation log read-only when present, and
// a friendly empty-state when the store has never consolidated.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryChangelogLane } from "./MemoryChangelogLane";

vi.mock("./api", () => ({ getMemoryConsolidationLog: vi.fn() }));
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
  test("renders the consolidation log Markdown when present", async () => {
    vi.mocked(api.getMemoryConsolidationLog).mockResolvedValue({
      text: "merged 3 facts",
      path: "/p/consolidation-log.md",
      folder_path: "/p",
    });
    renderLane();
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
});
