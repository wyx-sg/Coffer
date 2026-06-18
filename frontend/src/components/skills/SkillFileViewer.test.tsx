// frontend/src/components/skills/SkillFileViewer.test.tsx
// The skill file viewer renders Markdown nicely and shows other text raw,
// READ-ONLY: there is no Edit/Save flow. Instead it offers a FileActions bar
// (open/reveal in the desktop app; copy-path in the browser/jsdom).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SkillFileViewer } from "./SkillFileViewer";
import type { SkillFileContentOut } from "@/lib/api/skills";

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkillFileContent: vi.fn(),
}));

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
      size: 0,
      ...data,
    },
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof useSkillFileContent>);
}

describe("SkillFileViewer", () => {
  beforeEach(() => contentMock.mockReset());

  test("renders a .md file as rendered Markdown, not raw text", () => {
    stubContent({ path: "SKILL.md", content: "# Heading\n\nbody" });
    render(<SkillFileViewer name="s" path="SKILL.md" />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
  });

  test("is read-only: no Edit/Save controls, but offers the copy-path affordance", () => {
    stubContent({ path: "SKILL.md", content: "old" });
    render(<SkillFileViewer name="s" path="SKILL.md" />);

    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    // jsdom is not Tauri, so FileActions shows the copy-path fallback.
    expect(screen.getByRole("button", { name: /copy path/i })).toBeInTheDocument();
  });

  test("a truncated file stays read-only (no Edit button)", () => {
    stubContent({ path: "big.txt", content: "aaa", truncated: true });
    render(<SkillFileViewer name="s" path="big.txt" />);
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy path/i })).toBeInTheDocument();
  });
});
