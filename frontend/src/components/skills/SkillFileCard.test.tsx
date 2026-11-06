// frontend/src/components/skills/SkillFileCard.test.tsx
// The Files card (canvas 4.3.01, 4.3.12; Foundations 0.6.04) of a managed skill
// (SkillFileTree). It is read-only: Reveal
// in the tree's header, Open in editor over the file, no Edit. SKILL.md is first, then folders, then files; the open
// file is kept in `?file=`.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import type { SkillFileContentOut, SkillFileNode } from "@/lib/api/skills";
import { SkillFileTree } from "./SkillFileTree";

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

describe("a managed skill's Files card", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(skillsApi.filesTree).mockResolvedValue({ root: ROOT } as never);
    vi.mocked(skillsApi.fileContent).mockResolvedValue(content());
  });

  test("an imported skill's folder has no lock; the built-in one is locked file by file", async () => {
    const { unmount } = wrap(<SkillFileTree uid="sk-1" owner="deep-research" />);
    await screen.findByText("deep-research/SKILL.md");
    expect(screen.queryByRole("img", { name: /read-only/ })).not.toBeInTheDocument();
    unmount();
    wrap(<SkillFileTree uid="sk-1" owner="coffer-guide" builtin />);
    await screen.findByText("coffer-guide/SKILL.md");
    expect(screen.getByRole("img", { name: "Written by Coffer — read-only" })).toBeInTheDocument();
  });

  test("an open file has no Edit and no unsaved state, only Open in editor and Reveal", async () => {
    wrap(<SkillFileTree uid="sk-1" owner="deep-research" />);
    expect(await screen.findByRole("button", { name: "Open in editor" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Reveal in Finder" })).toHaveLength(2);
    const row = screen.getByRole("treeitem", { name: /SKILL\.md/ });
    expect(within(row).queryByRole("img", { name: "Unsaved changes" })).not.toBeInTheDocument();
  });

  describe("a deep tree", () => {
    // synced/<id>/{docx/scripts/office/x.xsd, pptx/SKILL.md}: no root SKILL.md.
    const DEEP = node("", "dir", [
      node(
        "abc",
        "dir",
        [
          node(
            "docx",
            "dir",
            [
              node(
                "scripts",
                "dir",
                [
                  node(
                    "office",
                    "dir",
                    [node("a.xsd", "file", [], "abc/docx/scripts/office/a.xsd")],
                    "abc/docx/scripts/office",
                  ),
                ],
                "abc/docx/scripts",
              ),
            ],
            "abc/docx",
          ),
          node("pptx", "dir", [node("SKILL.md", "file", [], "abc/pptx/SKILL.md")], "abc/pptx"),
        ],
        "abc",
      ),
    ]);
    const names = () => screen.getAllByRole("treeitem").map((r) => r.textContent);
    const renderDeep = async () => {
      vi.mocked(skillsApi.filesTree).mockResolvedValue({ root: DEEP } as never);
      wrap(<SkillFileTree uid="sk-1" owner="synced" />);
      await screen.findByRole("treeitem", { name: "abc" });
    };

    test("a folder toggles in place, and a file opens without collapsing its folders", async () => {
      await renderDeep();
      expect(names()).toEqual(["abc", "docx", "pptx"]);
      fireEvent.click(screen.getByRole("treeitem", { name: "pptx" }));
      expect(names()).toEqual(["abc", "docx", "pptx", "SKILL.md"]);
      fireEvent.click(screen.getByRole("treeitem", { name: "docx" }));
      fireEvent.click(screen.getByRole("treeitem", { name: "scripts" }));
      fireEvent.click(screen.getByRole("treeitem", { name: "office" }));
      expect(names()).toEqual(["abc", "docx", "scripts", "office", "a.xsd", "pptx", "SKILL.md"]);

      // Opening a file keeps every folder the user opened open.
      fireEvent.click(screen.getByRole("treeitem", { name: "a.xsd" }));
      expect(screen.getByTestId("where")).toHaveTextContent(
        "abc%2Fdocx%2Fscripts%2Foffice%2Fa.xsd",
      );
      expect(names()).toEqual(["abc", "docx", "scripts", "office", "a.xsd", "pptx", "SKILL.md"]);
      expect(screen.getByRole("treeitem", { name: "a.xsd" })).toHaveAttribute(
        "aria-selected",
        "true",
      );

      // A folder on the way to the open file can still be closed.
      fireEvent.click(screen.getByRole("treeitem", { name: "scripts" }));
      expect(names()).toEqual(["abc", "docx", "scripts", "pptx", "SKILL.md"]);
    });

    test("a folder shows its path as a tooltip", async () => {
      await renderDeep();
      expect(screen.getByRole("treeitem", { name: "docx" })).toHaveAttribute("title", "abc/docx");
    });
  });
});
