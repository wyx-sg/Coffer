// frontend/src/components/knowledge/KnowledgeIndexStatus.test.tsx
//
// Says when ranked search is degraded (spec knowledge FR-060/FR-061):
// unavailable (no internal connection) points at Settings rather than
// offering a rebuild that cannot help; stale-but-available offers the
// rebuild and shows it running; fully indexed and available renders nothing.
// `useIndexStatus`/`useRebuildIndex` run as REAL react-query hooks against
// the mocked wire layer.
import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { KnowledgeIndexStatus } from "./KnowledgeIndexStatus";

vi.mock("@/kinds/knowledge/api", () => ({
  getIndexStatus: vi.fn(),
  rebuildIndex: vi.fn(),
}));

const { getIndexStatus, rebuildIndex } = await import("@/kinds/knowledge/api");
const getIndexStatusMock = vi.mocked(getIndexStatus);
const rebuildIndexMock = vi.mocked(rebuildIndex);

afterEach(() => vi.clearAllMocks());

function renderStatus() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <KnowledgeIndexStatus />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("KnowledgeIndexStatus", () => {
  test("available: false points at Settings, not the rebuild", async () => {
    getIndexStatusMock.mockResolvedValue({
      available: false,
      files_indexed: 0,
      files_total: 12,
      path: "/Users/dev/.coffer/knowledge/.index",
    });
    renderStatus();

    expect(await screen.findByTestId("knowledge-index-status")).toBeInTheDocument();
    const settingsLink = screen.getByRole("link", { name: /settings/i });
    expect(settingsLink).toHaveAttribute("href", "/settings/engine");
    expect(screen.queryByRole("button", { name: /rebuild/i })).toBeNull();
  });

  test("a stale-but-available index offers the rebuild and shows progress", async () => {
    getIndexStatusMock.mockResolvedValue({
      available: true,
      files_indexed: 8,
      files_total: 12,
      path: "/Users/dev/.coffer/knowledge/.index",
    });
    let resolveRebuild: (v: {
      available: boolean;
      files_indexed: number;
      files_total: number;
      path: string;
    }) => void = () => {};
    rebuildIndexMock.mockReturnValue(
      new Promise((resolve) => {
        resolveRebuild = resolve;
      }),
    );
    renderStatus();

    const rebuildButton = await screen.findByRole("button", { name: /rebuild/i });
    rebuildButton.click();

    // The mutation's own isPending state IS the progress indicator: the
    // backend rebuild is synchronous, so there is no separate poll.
    await waitFor(() => expect(rebuildButton).toBeDisabled());
    expect(rebuildIndexMock).toHaveBeenCalledTimes(1);

    resolveRebuild({
      available: true,
      files_indexed: 12,
      files_total: 12,
      path: "/Users/dev/.coffer/knowledge/.index",
    });
    // Fully indexed now — the banner clears itself rather than nagging.
    await waitFor(() => expect(screen.queryByTestId("knowledge-index-status")).toBeNull());
  });

  test("fully indexed and available renders nothing", () => {
    getIndexStatusMock.mockResolvedValue({
      available: true,
      files_indexed: 5,
      files_total: 5,
      path: "/Users/dev/.coffer/knowledge/.index",
    });
    const { container } = renderStatus();
    expect(container).toBeEmptyDOMElement();
  });
});
