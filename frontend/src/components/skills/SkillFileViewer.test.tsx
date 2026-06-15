// frontend/src/components/skills/SkillFileViewer.test.tsx
// The skill file viewer renders Markdown nicely, shows other text raw, and
// supports editing (Edit → textarea → Save writes the new content).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SkillFileViewer } from "./SkillFileViewer";
import type { SkillFileContentOut } from "@/lib/api/skills";

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkillFileContent: vi.fn(),
  useWriteSkillFile: vi.fn(),
}));

const { useSkillFileContent, useWriteSkillFile } = await import("@/lib/hooks/useSkills");
const contentMock = vi.mocked(useSkillFileContent);
const writeMock = vi.mocked(useWriteSkillFile);

const mutate = vi.fn();

function stubContent(data: Partial<SkillFileContentOut>) {
  contentMock.mockReturnValue({
    data: {
      path: "SKILL.md",
      content: "",
      truncated: false,
      binary: false,
      size: 0,
      ...data,
    },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useSkillFileContent>);
}

beforeEach(() => {
  mutate.mockReset();
  writeMock.mockReturnValue({
    mutate,
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useWriteSkillFile>);
});

describe("SkillFileViewer", () => {
  test("renders a .md file as rendered Markdown, not raw text", () => {
    stubContent({ path: "SKILL.md", content: "# Heading\n\nbody" });
    render(<SkillFileViewer name="s" path="SKILL.md" />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
  });

  test("edits and saves a file", () => {
    stubContent({ path: "SKILL.md", content: "old" });
    render(<SkillFileViewer name="s" path="SKILL.md" />);

    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const textarea = screen.getByLabelText("SKILL.md") as HTMLTextAreaElement;
    expect(textarea.value).toBe("old");
    fireEvent.change(textarea, { target: { value: "new content" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(mutate).toHaveBeenCalledWith(
      { path: "SKILL.md", content: "new content" },
      expect.anything(),
    );
  });

  test("a truncated file is read-only (no Edit button)", () => {
    stubContent({ path: "big.txt", content: "aaa", truncated: true });
    render(<SkillFileViewer name="s" path="big.txt" />);
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });
});
