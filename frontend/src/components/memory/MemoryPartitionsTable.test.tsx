// frontend/src/components/memory/MemoryPartitionsTable.test.tsx
//
// The partitions list (spec memory "Show a partition's memories read-only"): a
// row per partition with its path ("Every project" for global) and its memory
// count, and a search box over name and path. No status control, no selection:
// every partition is served to every agent. Only a partition whose repository is gone offers Delete, and
// the delete goes through the kind-agnostic resource route after a confirm.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { pathText } from "@/test/truncatedPath";
import { MemoryPartitionsTable } from "./MemoryPartitionsTable";
import { COFFER, GLOBAL, GONE } from "./memoryTestData";

vi.mock("@/lib/api/resources", () => ({ resourcesApi: { remove: vi.fn() } }));
const { resourcesApi } = await import("@/lib/api/resources");
const removeMock = vi.mocked(resourcesApi.remove);

function renderTable(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

describe("MemoryPartitionsTable", () => {
  // A braced body: an arrow that returns the mock would hand vitest a
  // teardown function, and it would call the failing mock after the test.
  beforeEach(() => {
    removeMock.mockReset();
  });

  test("each row carries its path and its memories; global reads Every project", () => {
    renderTable(<MemoryPartitionsTable rows={[GLOBAL, COFFER]} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(expect.arrayContaining(["Partition", "Path", "Memories"]));
    const global = within(screen.getByText("global").closest("tr") as HTMLElement);
    expect(global.getByText("Every project")).toBeInTheDocument();
    expect(global.getByText("12")).toBeInTheDocument();
    const coffer = within(
      screen
        .getByText("coffer", { selector: "[data-truncated-text]" })
        .closest("tr") as HTMLElement,
    );
    expect(coffer.getByText(pathText("~/work/coffer"))).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search partitions")).toBeInTheDocument();
  });

  test("only a partition whose repository is gone is marked and offers Delete", () => {
    renderTable(<MemoryPartitionsTable rows={[COFFER, GONE]} />);
    const gone = within(
      screen
        .getByText("old-prototype", { selector: "[data-truncated-text]" })
        .closest("tr") as HTMLElement,
    );
    expect(gone.getByTestId("partition-unresolvable-badge")).toHaveTextContent(
      /repository missing/i,
    );
    expect(gone.getByRole("button", { name: /delete: old-prototype/i })).toBeInTheDocument();
    const coffer = within(
      screen
        .getByText("coffer", { selector: "[data-truncated-text]" })
        .closest("tr") as HTMLElement,
    );
    expect(coffer.queryByRole("button", { name: /delete/i })).toBeNull();
    expect(coffer.queryByTestId("partition-unresolvable-badge")).toBeNull();
  });

  acceptance("memory", "deleting a partition still asks", async () => {
    removeMock.mockResolvedValue(undefined);
    renderTable(<MemoryPartitionsTable rows={[COFFER, GONE]} />);
    fireEvent.click(screen.getByRole("button", { name: /delete: old-prototype/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete old-prototype?")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/deletes its 6 distilled memories and stops delivering them/i),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(/own memory for that folder is not touched/i),
    ).toBeInTheDocument();
    expect(removeMock).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Delete partition" }));
    await waitFor(() => expect(removeMock).toHaveBeenCalledWith(GONE.uid));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("a failed delete keeps the dialog open with its reason", async () => {
    removeMock.mockRejectedValue(new Error("disk is read-only"));
    renderTable(<MemoryPartitionsTable rows={[GONE]} />);
    fireEvent.click(screen.getByRole("button", { name: /delete: old-prototype/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete partition" }));
    expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  acceptance("web-ui", "a kind that cannot be disabled shows no status control", () => {
    renderTable(<MemoryPartitionsTable rows={[GLOBAL, COFFER]} />);
    expect(screen.queryByTestId("scope-control")).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^status$/i })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /^reach$/i })).toBeNull();
    expect(screen.queryByRole("combobox", { name: /^status$/i })).toBeNull();
    // No selection either: with no bulk action there is nothing to select for.
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
