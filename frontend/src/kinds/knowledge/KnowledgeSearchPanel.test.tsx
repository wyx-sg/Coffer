// frontend/src/kinds/knowledge/KnowledgeSearchPanel.test.tsx
//
// Literal search over the collection in view (spec knowledge FR-024/FR-060).
// `useKnowledgeSearch` runs as a REAL react-query mutation against the mocked
// wire layer, so the component's own rendering and empty-state handling are
// what's under test — not a mocked hook's return value.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { KnowledgeSearchPanel } from "./KnowledgeSearchPanel";

vi.mock("./api", () => ({
  search: vi.fn(),
}));

const { search } = await import("./api");
const searchMock = vi.mocked(search);

afterEach(() => vi.clearAllMocks());

function renderPanel(onSelectPath: (path: string) => void = () => {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <KnowledgeSearchPanel collection="shopee" onSelectPath={onSelectPath} />
    </QueryClientProvider>,
  );
}

function submitQuery(text: string) {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /search/i }));
}

describe("KnowledgeSearchPanel", () => {
  test("a result shows title, description, path and matching lines", async () => {
    searchMock.mockResolvedValue({
      results: [
        {
          path: "shopee/gateway.md",
          title: "Account Gateway",
          description: "where account decisions are made",
          lines: [{ line_number: 3, line: "The orchestration layer." }],
        },
      ],
    });
    const onSelectPath = vi.fn();
    renderPanel(onSelectPath);

    submitQuery("account orchestration");

    expect(await screen.findByText("Account Gateway")).toBeInTheDocument();
    expect(screen.getByText("where account decisions are made")).toBeInTheDocument();
    expect(screen.getByText("shopee/gateway.md")).toBeInTheDocument();
    expect(screen.getByText(/The orchestration layer\./)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Account Gateway"));
    expect(onSelectPath).toHaveBeenCalledWith("shopee/gateway.md");
  });

  test("an answer carries no mode or score to mistake for ranking", async () => {
    searchMock.mockResolvedValue({
      results: [
        {
          path: "shopee/gateway.md",
          title: "Account Gateway",
          description: "where account decisions are made",
          lines: [{ line_number: 1, line: "gateway" }],
        },
      ],
    });
    renderPanel();

    submitQuery("gateway");

    expect(await screen.findByText("Account Gateway")).toBeInTheDocument();
    expect(screen.queryByText(/literal/i)).toBeNull();
    expect(screen.queryByText(/ranked/i)).toBeNull();
  });

  test("an empty result set is a normal state with its own message, not an error", async () => {
    searchMock.mockResolvedValue({ results: [] });
    renderPanel();

    submitQuery("nothing matches this");

    expect(await screen.findByText(/no results/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
