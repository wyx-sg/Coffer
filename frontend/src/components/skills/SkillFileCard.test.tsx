// frontend/src/components/skills/SkillFileCard.test.tsx
// The Files card (canvas 4.3.01, 4.3.12; Foundations 0.6.04) in its two forms: a
// managed skill's (SkillFileTree — editable, an unsaved file wears an accent
// dot) and the read-only one every folder Coffer doesn't own renders
// (SkillReadOnlyFiles — a lock on every file, Reveal in the tree's header, the
// reader without Edit). SKILL.md is first, then folders, then files; the open
// file is kept in `?file=`.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import type { SkillFileContentOut, SkillFileNode } from "@/lib/api/skills";
import { SkillFileTree } from "./SkillFileTree";
import { SkillReadOnlyFiles } from "./SkillReadOnlyFiles";

const revealMock = vi.fn(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: vi.fn(() => Promise.resolve()), reveal: revealMock }),
}));
vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    filesTree: vi.fn(),
    fileContent: vi.fn(),
    list: vi.fn(async () => ({ items: [] })),
    writeFileContent: vi.fn(),
  },
}));
const { skillsApi } = await import("@/lib/api/skills");

function node(name: string, type: "file" | "dir", children: SkillFileNode[] = [], path = name) {
  return {
    name,
    path,
    type,
    children,
    abs_path: `/skills/deep-research/${path}`,
    folder_abs_path: "/skills/deep-research",
    size: type === "file" ? 12 : null,
    truncated: false,
  } as SkillFileNode;
}

const ROOT = node("", "dir", [
  node("LICENSE", "file"),
  node("scripts", "dir", [node("search.py", "file", [], "scripts/search.py")]),
  node("SKILL.md", "file"),
]);

function content(over: Partial<SkillFileContentOut> = {}): SkillFileContentOut {
  return {
    path: "SKILL.md",
    abs_path: "/skills/deep-research/SKILL.md",
    folder_abs_path: "/skills/deep-research",
    content: "# Deep research\n\nbody",
    truncated: false,
    binary: false,
    size: 21,
    fingerprint: "fp-1",
    ...over,
  };
}

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.search}</output>;
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        {ui}
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("the read-only Files card", () => {
  beforeEach(() => vi.clearAllMocks());

  const tree = { isPending: false, error: null, data: ROOT };

  test("a header with the folder's name, a lock and Reveal; SKILL.md first, folders next, files last", () => {
    wrap(
      <SkillReadOnlyFiles
        name="deep-research"
        tree={tree}
        useContent={() => ({ isPending: false, error: null, data: content() })}
      />,
    );
    const nav = screen.getByRole("tree", { name: "Files" });
    const rows = within(nav).getAllByRole("treeitem");
    expect(rows.map((r) => r.textContent)).toEqual(["SKILL.md", "scripts", "search.py", "LICENSE"]);
    // Name and the lock's reason over the tree.
    expect(screen.getByText("deep-research", { selector: "span" })).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: "Not in your library — read-only" }),
    ).toBeInTheDocument();
    // A folder's name is sans, a file's is mono.
    expect(within(rows[1]).getByText("scripts")).not.toHaveClass("font-mono");
    expect(within(rows[0]).getByText("SKILL.md")).toHaveClass("font-mono");
    // Every file wears a lock; folders don't.
    expect(rows[0].querySelector("svg.lucide-lock")).not.toBeNull();
    expect(rows[1].querySelector("svg.lucide-lock")).toBeNull();
  });

  test("Reveal in Finder opens the folder", () => {
    wrap(
      <SkillReadOnlyFiles
        name="deep-research"
        tree={tree}
        useContent={() => ({ isPending: false, error: null, data: content() })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Reveal in Finder" }));
    expect(revealMock).toHaveBeenCalledWith("/skills/deep-research");
  });

  test("the reader has no Edit; opening a file writes it to ?file=", () => {
    const useContent = vi.fn((path: string) => ({
      isPending: false,
      error: null,
      data: content({ path, content: `text of ${path}` }),
    }));
    wrap(<SkillReadOnlyFiles name="deep-research" tree={tree} useContent={useContent} />);
    expect(screen.getByText("deep-research/SKILL.md")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("treeitem", { name: /search\.py/ }));
    expect(screen.getByTestId("where")).toHaveTextContent("?file=scripts%2Fsearch.py");
    expect(useContent).toHaveBeenLastCalledWith("scripts/search.py");
    expect(screen.getByText("deep-research/scripts/search.py")).toBeInTheDocument();
  });

  test("a binary file says so; a truncated one shows the grey bar", () => {
    const { unmount } = wrap(
      <SkillReadOnlyFiles
        name="deep-research"
        tree={tree}
        useContent={() => ({
          isPending: false,
          error: null,
          data: content({ binary: true, size: 49152 }),
        })}
      />,
    );
    expect(screen.getByText("Can’t preview binary file")).toBeInTheDocument();
    unmount();
    wrap(
      <SkillReadOnlyFiles
        name="deep-research"
        tree={tree}
        useContent={() => ({
          isPending: false,
          error: null,
          data: content({ truncated: true, content: "aaa", size: 18_000_000 }),
        })}
      />,
    );
    expect(screen.getByText(/read-only here/)).toBeInTheDocument();
  });
});

describe("a managed skill's Files card", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(skillsApi.filesTree).mockResolvedValue({ root: ROOT } as never);
    vi.mocked(skillsApi.fileContent).mockResolvedValue(content());
  });

  test("an editable folder has no lock; the built-in one is locked file by file", async () => {
    const { unmount } = wrap(<SkillFileTree uid="sk-1" owner="deep-research" />);
    await screen.findByText("deep-research/SKILL.md");
    expect(screen.queryByRole("img", { name: /read-only/ })).not.toBeInTheDocument();
    unmount();
    wrap(<SkillFileTree uid="sk-1" owner="coffer-guide" builtin />);
    await screen.findByText("coffer-guide/SKILL.md");
    expect(screen.getByRole("img", { name: "Written by Coffer — read-only" })).toBeInTheDocument();
  });

  test("a file with unsaved edits wears an accent dot in the tree", async () => {
    wrap(<SkillFileTree uid="sk-1" owner="deep-research" />);
    fireEvent.click(await screen.findByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "changed" } });
    const row = screen.getByRole("treeitem", { name: /SKILL\.md/ });
    expect(within(row).getByRole("img", { name: "Unsaved changes" })).toHaveClass("bg-accent");
  });
});
