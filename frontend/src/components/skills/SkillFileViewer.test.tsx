// frontend/src/components/skills/SkillFileViewer.test.tsx
// The right half of the Files tab card: a header bar (path, size, the file's
// actions) over the file. Markdown renders without its frontmatter, with a
// Preview / Source switch and Edit; other text shows its source with Edit and
// Open in editor; a binary file offers only open-with-its-app and reveal; a
// file the read could not load whole shows its start read-only. Editing saves
// conditionally, and a stale save keeps the text and offers Reload · Compare ·
// Copy my text.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";
import { SkillFileViewer } from "./SkillFileViewer";
import type { SkillFileContentOut } from "@/lib/api/skills";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkillFileContent: vi.fn(),
  useReadSkillFileNow: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: { writeFileContent: vi.fn() },
}));

const { skillsApi } = await import("@/lib/api/skills");
const writeMock = vi.mocked(skillsApi.writeFileContent);

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
      fingerprint: "fp-1",
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
    writeMock.mockReset();
  });

  test("SKILL.md opens rendered without its frontmatter, with Preview / Source and Edit", () => {
    stubContent({ content: "---\nname: s\ndescription: d\n---\n# Heading\n\nbody" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="SKILL.md" />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    expect(screen.queryByText("description")).not.toBeInTheDocument();
    expect(screen.getByText("2.3 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open in editor/i })).not.toBeInTheDocument();
  });

  test("another text file shows Edit and Open in editor", () => {
    stubContent({ path: "scripts/search.py", content: "print(1)" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="scripts/search.py" />);
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
  });

  test("a binary file offers its own app and Finder, and no editor", () => {
    stubContent({ path: "flow.png", binary: true, size: 49152 });
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="flow.png" />);
    expect(screen.getByText("Binary file · 48 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in default app/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
  });

  test("editing and saving sends the content with the fingerprint it read", async () => {
    stubContent({ content: "old", fingerprint: "fp-1" });
    writeMock.mockResolvedValue({ fingerprint: "fp-2" } as never);
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="SKILL.md" />);

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "new body" } });
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await vi.waitFor(() =>
      expect(writeMock).toHaveBeenCalledWith(SKILL_UID, {
        path: "SKILL.md",
        content: "new body",
        expected_fingerprint: "fp-1",
      }),
    );
  });

  test("⌘S saves while the text has focus", async () => {
    stubContent({ content: "old" });
    writeMock.mockResolvedValue({ fingerprint: "fp-2" } as never);
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="SKILL.md" />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "typed" } });
    fireEvent.keyDown(box, { key: "s", metaKey: true });
    await vi.waitFor(() => expect(writeMock).toHaveBeenCalledTimes(1));
  });

  acceptance(
    "web-ui",
    "a skill file changed on disk refuses the save and keeps the text",
    async () => {
      stubContent({ content: "old", fingerprint: "fp-1" });
      writeMock.mockRejectedValue(new ApiError("SKILL_FILE_STALE", "changed on disk"));
      renderViewer(<SkillFileViewer uid={SKILL_UID} path="SKILL.md" />);

      fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "my work" } });
      fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

      await vi.waitFor(() =>
        expect(screen.getByRole("alert")).toHaveTextContent(/changed on disk after you opened it/i),
      );
      expect(screen.getByText("Not saved")).toBeInTheDocument();
      expect(screen.getByRole("textbox")).toHaveValue("my work");
      for (const name of ["Reload", "Compare", "Copy my text"]) {
        expect(screen.getByRole("button", { name })).toBeInTheDocument();
      }
      expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    },
  );

  test("a truncated file shows its start read-only, with Open in editor", () => {
    stubContent({ path: "big.jsonl", content: "aaa", truncated: true, size: 18_000_000 });
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="big.jsonl" />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/too large to show or edit here/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });

  // spec skill-manager "Regenerate Coffer's builtin skill from the build": the
  // built-in banner above the files says why; the viewer offers no Edit.
  test("a builtin skill's files are read-only", () => {
    stubContent({ content: "# Guide" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} path="SKILL.md" builtin />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
