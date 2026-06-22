// frontend/src/kinds/memory/MemoryHandoffLane.test.tsx
//
// The Handoff lane lists per-branch scene notes; selecting a branch renders its
// note read-only. Empty store → friendly empty-state.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryHandoffLane } from "./MemoryHandoffLane";

vi.mock("./api", () => ({ getMemoryHandoff: vi.fn() }));
const api = await import("./api");

function renderLane() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryHandoffLane store="global" />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MemoryHandoffLane", () => {
  test("lists branches and renders the selected scene", async () => {
    vi.mocked(api.getMemoryHandoff).mockResolvedValue({
      scenes: [
        {
          branch: "feat/login",
          text: "left off mid-refactor",
          updated_at: "2026-06-22T00:00:00Z",
          path: "/p/feat-login.md",
          folder_path: "/p",
        },
      ],
    });
    renderLane();
    fireEvent.click(await screen.findByText("feat/login"));
    expect(await screen.findByText("left off mid-refactor")).toBeInTheDocument();
  });

  test("shows the empty-state when there are no handoff scenes", async () => {
    vi.mocked(api.getMemoryHandoff).mockResolvedValue({ scenes: [] });
    renderLane();
    expect(await screen.findByText(/no handoff notes yet/i)).toBeInTheDocument();
  });
});
