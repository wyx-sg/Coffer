// frontend/src/pages/AgentMemoryStorePage.test.tsx
//
// One native-memory store's page: the tree of the store directory, a read-only
// preview of the selected file, and the open / reveal actions that used to sit
// in the Memory table's "⋯" menu. The store is read from `?dir=` — the
// directory IS its identity — with `?project=` supplying only a readable
// heading.
//
// The two file hooks are mocked at the network boundary, as are the fs actions
// (their own suite covers the transport).
//
// The agent half of the route is its `uid` (`/agents/:uid/memory`), so the
// fixture route mounts a uid that is not the agent's name — the file reads and
// the back link both have to spell it.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AgentMemoryStorePage } from "./AgentMemoryStorePage";
import type { NativeMemoryFileContent, NativeMemoryFileNode } from "@/lib/api/agentNativeMemory";

vi.mock("@/lib/hooks/useAgentNativeMemory", () => ({
  useNativeMemoryFiles: vi.fn(),
  useNativeMemoryFileContent: vi.fn(),
}));

const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));

const hooks = await import("@/lib/hooks/useAgentNativeMemory");

const DIR = "/Users/xing/.claude/projects/-Users-xing-Coffer/memory";

const ROOT: NativeMemoryFileNode = {
  name: "memory",
  path: "",
  type: "dir",
  size: null,
  truncated: false,
  children: [
    {
      name: "MEMORY.md",
      path: "MEMORY.md",
      type: "file",
      size: 12,
      truncated: false,
      children: [],
    },
    {
      name: "port-drift.md",
      path: "port-drift.md",
      type: "file",
      size: 40,
      truncated: false,
      children: [],
    },
  ],
};

const CONTENT: NativeMemoryFileContent = {
  path: "port-drift.md",
  abs_path: `${DIR}/port-drift.md`,
  content: "# Port drift\n\nThe daemon moves ports on restart.",
  truncated: false,
  binary: false,
  size: 40,
};

function stubTree(root: NativeMemoryFileNode | null = ROOT) {
  vi.mocked(hooks.useNativeMemoryFiles).mockReturnValue({
    data: root ? { root } : undefined,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useNativeMemoryFiles>);
}

function stubContent(content: Partial<NativeMemoryFileContent> = {}) {
  vi.mocked(hooks.useNativeMemoryFileContent).mockReturnValue({
    data: { ...CONTENT, ...content },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useNativeMemoryFileContent>);
}

function renderAt(search = `?dir=${encodeURIComponent(DIR)}&project=%2FUsers%2Fxing%2FCoffer`) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agents/u-claude/memory${search}`]}>
        <Routes>
          <Route path="/agents/:uid/memory" element={<AgentMemoryStorePage />} />
          <Route path="/agents/:uid" element={<div>agent detail</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("AgentMemoryStorePage", () => {
  test("reads the store named by ?dir= and heads the page with the readable label", () => {
    stubTree();
    stubContent();
    renderAt();
    expect(vi.mocked(hooks.useNativeMemoryFiles)).toHaveBeenCalledWith("u-claude", DIR);
    expect(screen.getByRole("heading", { name: "/Users/xing/Coffer" })).toBeInTheDocument();
    expect(screen.getByText(DIR)).toBeInTheDocument();
  });

  test("shows the store's files and previews the one you select", () => {
    stubTree();
    stubContent();
    renderAt();

    expect(screen.getByText("MEMORY.md")).toBeInTheDocument();
    // Nothing is previewed until a file is chosen.
    expect(screen.getByText(/select a file to view/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText("port-drift.md"));
    expect(vi.mocked(hooks.useNativeMemoryFileContent).mock.calls.at(-1)).toEqual([
      "u-claude",
      DIR,
      "port-drift.md",
    ]);
    expect(screen.getByText(/the daemon moves ports on restart/i)).toBeInTheDocument();
  });

  test("offers open-in-editor and reveal on the previewed file", () => {
    // The affordances that left the Memory table's ⋯ menu land here.
    stubTree();
    stubContent();
    renderAt();
    fireEvent.click(screen.getByText("port-drift.md"));

    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    expect(openMock).toHaveBeenCalledWith(CONTENT.abs_path, expect.anything());
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    expect(revealMock).toHaveBeenCalledWith(CONTENT.abs_path);
  });

  test("the preview never offers a save — the agent owns these files", () => {
    stubTree();
    stubContent();
    renderAt();
    fireEvent.click(screen.getByText("port-drift.md"));
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
  });

  test("a truncated file says the preview is only its start", () => {
    stubTree();
    stubContent({ truncated: true });
    renderAt();
    fireEvent.click(screen.getByText("port-drift.md"));
    expect(screen.getByText(/content truncated/i)).toBeInTheDocument();
  });

  test("a URL with no store says so instead of querying for nothing", () => {
    stubTree();
    stubContent();
    renderAt("");
    expect(screen.getByRole("alert")).toHaveTextContent(/no memory store was named/i);
  });

  // The back affordance is the shared PageHeader's, so it is a real link with
  // an href — middle-clickable, copyable — not a button that calls navigate().
  test("back returns to the agent's Memory tab", () => {
    stubTree();
    stubContent();
    renderAt();
    const back = screen.getByRole("link", { name: /back to/i });
    expect(back).toHaveAttribute("href", "/agents/u-claude?tab=memory");
    fireEvent.click(back);
    expect(screen.getByText("agent detail")).toBeInTheDocument();
  });
});
