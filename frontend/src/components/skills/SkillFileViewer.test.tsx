// frontend/src/components/skills/SkillFileViewer.test.tsx
// The skill file viewer renders Markdown nicely and shows other text raw. It
// reads by default and edits behind an explicit Edit, and still offers a
// FileActions bar (open in editor / reveal in file manager — daemon-backed) for
// edits that want a real editor. Files the read could not load whole stay
// read-only: saving a partial read would truncate the file on disk.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";
import { SkillFileViewer } from "./SkillFileViewer";
import type { SkillFileContentOut } from "@/lib/api/skills";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkillFileContent: vi.fn(),
}));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: { writeFileContent: vi.fn() },
}));

const { skillsApi } = await import("@/lib/api/skills");
const writeMock = vi.mocked(skillsApi.writeFileContent);

// The editor saves through a react-query mutation, so the tree needs a client.
function renderViewer(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

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

  test("renders a .md file as rendered Markdown, not raw text", () => {
    stubContent({ path: "SKILL.md", content: "# Heading\n\nbody" });
    renderViewer(<SkillFileViewer name="s" path="SKILL.md" />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
  });

  test("reads by default: Edit is offered, Save is not, and open/reveal stay", () => {
    stubContent({ path: "SKILL.md", content: "old" });
    renderViewer(<SkillFileViewer name="s" path="SKILL.md" />);

    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    // FileActions offers real open/reveal on both surfaces (daemon-backed on web).
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal/i })).toBeInTheDocument();
  });

  test("editing and saving sends the content with the fingerprint it read", async () => {
    stubContent({ path: "SKILL.md", content: "old", fingerprint: "fp-1" });
    writeMock.mockResolvedValue({ fingerprint: "fp-2" } as never);
    renderViewer(<SkillFileViewer name="s" path="SKILL.md" />);

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "new body" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await vi.waitFor(() =>
      expect(writeMock).toHaveBeenCalledWith("s", {
        path: "SKILL.md",
        content: "new body",
        expected_fingerprint: "fp-1",
      }),
    );
  });

  test("Save is disabled until the text actually changes", () => {
    stubContent({ path: "SKILL.md", content: "old" });
    renderViewer(<SkillFileViewer name="s" path="SKILL.md" />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  test("a stale save is reported and the typed text survives", async () => {
    stubContent({ path: "SKILL.md", content: "old", fingerprint: "fp-1" });
    writeMock.mockRejectedValue(new ApiError("SKILL_FILE_STALE", "changed on disk"));
    renderViewer(<SkillFileViewer name="s" path="SKILL.md" />);

    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "my work" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await vi.waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/changed on disk/i));
    expect(screen.getByRole("textbox")).toHaveValue("my work");
    expect(screen.getByRole("button", { name: /discard my edits/i })).toBeInTheDocument();
  });

  test("a truncated file stays read-only — a save would cut it short on disk", () => {
    stubContent({ path: "big.txt", content: "aaa", truncated: true });
    renderViewer(<SkillFileViewer name="s" path="big.txt" />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
  });
});
