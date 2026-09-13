// frontend/src/kinds/knowledge/KnowledgeSearchPanel.test.tsx
//
// Ranked search over the collection in view (spec knowledge FR-024/FR-060,
// web surface FR-061). `useKnowledgeSearch` runs as a REAL react-query
// mutation against the mocked wire layer, so the component's own literal-vs-
// ranked labelling and empty-state handling are what's under test — not a
// mocked hook's return value.
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
  test("a ranked result shows title, description, path and matching lines", async () => {
    searchMock.mockResolvedValue({
      mode: "ranked",
      reason: "",
      results: [
        {
          path: "shopee/gateway.md",
          title: "Account Gateway",
          description: "where account decisions are made",
          score: 0.83,
          heading: "Overview",
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
    // No literal-mode notice on a ranked answer.
    expect(screen.queryByText(/literal/i)).toBeNull();

    fireEvent.click(screen.getByText("Account Gateway"));
    expect(onSelectPath).toHaveBeenCalledWith("shopee/gateway.md");
  });

  test("a literal-mode answer is labelled as such, with its reason — never mistaken for ranked", async () => {
    searchMock.mockResolvedValue({
      mode: "literal",
      reason: "no internal connection",
      results: [
        {
          path: "shopee/gateway.md",
          title: "Account Gateway",
          description: "where account decisions are made",
          score: null,
          heading: "",
          lines: [{ line_number: 1, line: "gateway" }],
        },
      ],
    });
    renderPanel();

    submitQuery("gateway");

    expect(await screen.findByText(/literal/i)).toBeInTheDocument();
    // The reason accompanies the notice, not just a bare "degraded" label.
    expect(screen.getByText(/internal connection/i)).toBeInTheDocument();
  });

  test("an empty result set is a normal state with its own message, not an error", async () => {
    searchMock.mockResolvedValue({ mode: "ranked", reason: "", results: [] });
    renderPanel();

    submitQuery("nothing matches this");

    expect(await screen.findByText(/no results/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
