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
// The page is addressed by the agent's TYPE (`/agents/:type/memory/store`);
// `useAgentRoute` turns it into the uid every read is keyed by, and is mocked
// here with a uid that is not the type — the reads have to spell the uid, the
// back link the type.

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AgentMemoryStorePage } from "./AgentMemoryStorePage";
import type { NativeMemoryFileContent, NativeMemoryFileNode } from "@/lib/api/agentNativeMemory";

vi.mock("@/lib/hooks/useAgentNativeMemory", async (importOriginal) => ({
  countMemoryFiles: (await importOriginal<typeof import("@/lib/hooks/useAgentNativeMemory")>())
    .countMemoryFiles,
  useNativeMemoryFiles: vi.fn(),
  useNativeMemoryFileContent: vi.fn(),
}));

const openMock = vi.fn(() => Promise.resolve());
const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: revealMock }),
}));

vi.mock("@/lib/hooks/useAgentRoute", () => ({
  useAgentRoute: () => ({
    type: "claude_code",
    typeRow: undefined,
    uid: "agt_01cc",
    agent: undefined,
    isPending: false,
    error: null,
    notAdded: false,
  }),
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

function renderAt(
  search = `?dir=${encodeURIComponent(DIR)}&project=${encodeURIComponent("/Users/xing/Coffer")}`,
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/agents/claude_code/memory/store${search}`]}>
        <Routes>
          <Route path="/agents/:type/memory/store" element={<AgentMemoryStorePage />} />
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
    expect(vi.mocked(hooks.useNativeMemoryFiles)).toHaveBeenCalledWith("agt_01cc", DIR);
    expect(screen.getByRole("heading", { name: "~/Coffer" })).toBeInTheDocument();
    expect(screen.getByText("Claude Code native memory store · 2 files")).toBeInTheDocument();
    expect(screen.getByText("Files · 2")).toBeInTheDocument();
  });

  test("shows the store's files and previews the one you select", () => {
    stubTree();
    stubContent();
    renderAt();

    // The store's index opens first.
    expect(vi.mocked(hooks.useNativeMemoryFileContent).mock.calls[0]).toEqual([
      "agt_01cc",
      DIR,
      "MEMORY.md",
    ]);
    expect(screen.getByText(/index claude code loads at session start/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText("port-drift.md"));
    expect(vi.mocked(hooks.useNativeMemoryFileContent).mock.calls.at(-1)).toEqual([
      "agt_01cc",
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
    expect(screen.getByText("Read-only")).toBeInTheDocument();
    expect(screen.getByText(/claude code owns these files and rewrites them/i)).toBeInTheDocument();
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
    expect(screen.getByText(/no memory store was named/i)).toBeInTheDocument();
  });
});
