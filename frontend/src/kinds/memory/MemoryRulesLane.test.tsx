// frontend/src/kinds/memory/MemoryRulesLane.test.tsx
//
// The Rules lane is a single curated doc, shown through the shared file-tree
// lane as one file row: select it to preview the Markdown read-only; an absent
// store shows a friendly empty-state. The preview offers a delete action with a
// confirm dialog wired to the rules DELETE helper.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRulesLane } from "./MemoryRulesLane";

vi.mock("./api", () => ({ getMemoryRules: vi.fn(), deleteMemoryRules: vi.fn() }));
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
  test("renders the rules Markdown when a row is selected", async () => {
    vi.mocked(api.getMemoryRules).mockResolvedValue({ text: "always run lint" });
    renderLane();
    fireEvent.click(await screen.findByRole("button", { name: /^Rules$/ }));
    expect(await screen.findByText("always run lint")).toBeInTheDocument();
  });

  test("shows the empty-state when the store has no rules", async () => {
    vi.mocked(api.getMemoryRules).mockResolvedValue({ text: null });
    renderLane();
    expect(await screen.findByText(/no rules yet/i)).toBeInTheDocument();
  });

  test("delete asks for confirmation then calls the rules DELETE helper", async () => {
    vi.mocked(api.getMemoryRules).mockResolvedValue({ text: "always run lint" });
    vi.mocked(api.deleteMemoryRules).mockResolvedValue();
    renderLane();
    fireEvent.click(await screen.findByRole("button", { name: /^Rules$/ }));
    // The preview toolbar carries a destructive delete (rules has no file path,
    // so only the delete button is present).
    fireEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api.deleteMemoryRules).toHaveBeenCalledWith("global"));
  });
});
