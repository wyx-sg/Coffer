// frontend/src/components/skills/SkillFileViewer.test.tsx
// The right half of the Files tab card (canvas 4.3.12–4.3.16, 4.3.40), read-only:
// the 40px toolbar (path under the skill's name, size, Open in editor and Reveal
// in Finder) over the file. Markdown renders with its front matter as a key /
// value block and a Preview / Source switch; code shows its text with a wrap
// toggle; a binary file says it can't be previewed and offers Reveal in Finder; a
// file the read could not load whole shows its start under a grey bar. A skill's
// files are changed in the person's own editor, so there is no Edit, no Save and
// no unsaved state.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";
import { SkillFileViewer } from "./SkillFileViewer";
import type { SkillFileContentOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";

const fs = vi.hoisted(() => ({
  open: vi.fn(() => Promise.resolve()),
  reveal: vi.fn(() => Promise.resolve()),
}));
vi.mock("@/lib/fsActions", () => ({ useFsActions: () => fs }));
vi.mock("@/lib/hooks/useSkills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useSkills")>()),
  useSkillFileContent: vi.fn(),
}));

function renderViewer(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

const SKILL_UID = "sk-91c4";

const { useSkillFileContent } = await import("@/lib/hooks/useSkills");
const contentMock = vi.mocked(useSkillFileContent);

function stubContent(data: Partial<SkillFileContentOut>) {
  contentMock.mockReturnValue({
    data: {
      path: "SKILL.md",
      abs_path: "/skills/s/SKILL.md",
      folder_abs_path: "/skills/s",
      content: "",
      truncated: false,
      binary: false,
      size: 2355,
      ...data,
    },
    isPending: false,
    error: null,
    refetch: vi.fn(async () => ({})),
  } as unknown as ReturnType<typeof useSkillFileContent>);
}

describe("SkillFileViewer", () => {
  beforeEach(() => {
    contentMock.mockReset();
    vi.clearAllMocks();
  });

  test("SKILL.md opens rendered with its front matter and a Preview / Source switch", () => {
    stubContent({ content: "---\nname: s\ndescription: d\n---\n# Heading\n\nbody" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    // The front matter is a key / value block above the title.
    const meta = screen.getByTestId("front-matter");
    expect(meta).toHaveTextContent("description");
    expect(meta).toHaveTextContent("d");
    expect(screen.getByText("demo/SKILL.md")).toBeInTheDocument();
    expect(screen.getByText("2.3 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: /wrap lines/i })).not.toBeInTheDocument();
  });

  acceptance("web-ui", "a skill file is read-only in the Files tab", () => {
    stubContent({ path: "scripts/search.py", content: "print(1)" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="scripts/search.py" />);
    expect(screen.getByText("demo/scripts/search.py")).toBeInTheDocument();
    // The header bar opens the file in the person's editor and reveals it.
    fireEvent.click(screen.getByRole("button", { name: "Open in editor" }));
    expect(fs.open).toHaveBeenCalledWith("/skills/s/SKILL.md", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Reveal in Finder" }));
    expect(fs.reveal).toHaveBeenCalledWith("/skills/s/SKILL.md");
    // The body is read-only: no Edit, no Save, no editable field, no unsaved state.
    expect(screen.queryByRole("button", { name: /^(edit|save)$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-readonly", "true");
    expect(screen.queryByText(/unsaved|not saved/i)).not.toBeInTheDocument();
    // Code keeps its wrap toggle.
    const wrap = screen.getByRole("button", { name: /wrap lines/i });
    expect(wrap).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(wrap);
    expect(wrap).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
  });

  test("a binary file says it can't be previewed and offers Reveal in Finder", () => {
    stubContent({ path: "flow.png", binary: true, size: 49152 });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="flow.png" />);
    expect(screen.getByText("Can’t preview binary file")).toBeInTheDocument();
    expect(screen.getByText("flow.png · 48 KB")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /reveal in finder/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
  });

  test("a truncated file shows its start under a grey bar with Open in editor", () => {
    stubContent({ path: "big.jsonl", content: "aaa", truncated: true, size: 18_000_000 });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="big.jsonl" />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Showing the first 3 B of 17.2 MB/i)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /open in editor/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
