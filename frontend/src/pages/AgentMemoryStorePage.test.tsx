// frontend/src/pages/AgentMemoryStorePage.test.tsx
//
// One native-memory store's page (boards 2.1.51, 2.1.61): the standard detail
// header with Reveal in Finder, the tree of the store directory (read-only: a
// lock in its header and a row menu with Copy path and Reveal in Finder), and
// the viewer of the selected file (path, Preview / Source, Open in editor). The store is read from `?dir=` — the
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
import { fireEvent, render, screen, within } from "@testing-library/react";
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
    expect(screen.getByRole("heading", { name: /~\/Coffer/ })).toBeInTheDocument();
    expect(screen.getByText("Claude Code memory · 2 files · read-only")).toBeInTheDocument();
    // The tree's header strip says "Files" with a lock, and no count.
    expect(screen.getByText("Files")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Read-only" })).toBeInTheDocument();
    expect(screen.queryByText("Files · 2")).not.toBeInTheDocument();
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
    // No hint line about the index, no ownership footer.
    expect(screen.queryByText(/index claude code loads/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/owns these files/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("port-drift.md"));
    expect(vi.mocked(hooks.useNativeMemoryFileContent).mock.calls.at(-1)).toEqual([
      "agt_01cc",
      DIR,
      "port-drift.md",
    ]);
    expect(screen.getByText(/the daemon moves ports on restart/i)).toBeInTheDocument();
    // The toolbar names the file by its path, home-abbreviated.
    expect(
      screen.getByText("~/.claude/projects/-Users-xing-Coffer/memory/port-drift.md"),
    ).toBeInTheDocument();
  });

  test("the viewer offers Open in editor; the header reveals the store's folder", () => {
    stubTree();
    stubContent();
    renderAt();
    fireEvent.click(screen.getByText("port-drift.md"));

    fireEvent.click(screen.getByRole("button", { name: /open in editor/i }));
    expect(openMock).toHaveBeenCalledWith(CONTENT.abs_path, expect.anything());
    // One Reveal on the page: the header's, for the folder.
    fireEvent.click(screen.getByRole("button", { name: /reveal in finder/i }));
    expect(revealMock).toHaveBeenCalledWith(DIR);
  });

  test("a row's menu copies its path or reveals it", async () => {
    stubTree();
    stubContent();
    const writeText = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: "More for port-drift.md" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Copy path" }));
    expect(writeText).toHaveBeenCalledWith(`${DIR}/port-drift.md`);
    fireEvent.click(screen.getByRole("button", { name: "More for port-drift.md" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Reveal in Finder" }));
    expect(revealMock).toHaveBeenCalledWith(`${DIR}/port-drift.md`);
  });

  test("Markdown front matter reads as a key / value grid above the body", () => {
    stubTree();
    stubContent({
      content: "---\nname: port-drift\ntype: feedback\n---\n# Port drift\n\nBody.",
    });
    renderAt();
    fireEvent.click(screen.getByText("port-drift.md"));
    const grid = within(screen.getByTestId("front-matter"));
    expect(grid.getByText("name")).toBeInTheDocument();
    expect(grid.getByText("feedback")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Port drift" })).toBeInTheDocument();
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
    expect(screen.getByText(/no memory store was named/i)).toBeInTheDocument();
  });
});
