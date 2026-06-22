// frontend/src/kinds/memory/MemoryRulesLane.test.tsx
//
// The Rules lane is a single curated doc: render the Markdown read-only when
// present, a friendly empty-state when the store has none.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRulesLane } from "./MemoryRulesLane";

vi.mock("./api", () => ({ getMemoryRules: vi.fn() }));
const api = await import("./api");

function renderLane() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRulesLane store="global" />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("MemoryRulesLane", () => {
  test("renders the rules Markdown when present", async () => {
    vi.mocked(api.getMemoryRules).mockResolvedValue({ text: "always run lint" });
    renderLane();
    expect(await screen.findByText("always run lint")).toBeInTheDocument();
  });

  test("shows the empty-state when the store has no rules", async () => {
    vi.mocked(api.getMemoryRules).mockResolvedValue({ text: null });
    renderLane();
    expect(await screen.findByText(/no rules yet/i)).toBeInTheDocument();
  });
});
