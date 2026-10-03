// frontend/src/components/skills/SkillFileViewer.test.tsx
// The right half of the Files tab card (canvas 4.3.12–4.3.16, 4.3.40): the
// 40px toolbar (path under the skill's name, size, the file's actions) over the
// file. Markdown renders with its front matter as a key / value block, a
// Preview / Source switch and Edit; code shows its text with a wrap toggle and
// Edit; a binary file says it can't be previewed and offers Reveal in Finder; a
// file the read could not load whole shows its start under a grey bar, read-only.
// Editing saves conditionally; a stale save keeps the text and offers Compare…
// (the 1060 two-way choice) and Copy my text; Cancel over a changed file asks
// "Discard your edit to SKILL.md?".
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren, ReactNode } from "react";
import { SkillFileViewer } from "./SkillFileViewer";
import type { SkillFileContentOut } from "@/lib/api/skills";
import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/hooks/useSkills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/hooks/useSkills")>()),
  useSkillFileContent: vi.fn(),
  useReadSkillFileNow: vi.fn(),
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

const { useSkillFileContent, useReadSkillFileNow } = await import("@/lib/hooks/useSkills");
const contentMock = vi.mocked(useSkillFileContent);
const readNowMock = vi.mocked(useReadSkillFileNow);

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
    readNowMock.mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
  });

  test("SKILL.md opens rendered with its front matter, a Preview / Source switch and Edit", () => {
    stubContent({ content: "---\nname: s\ndescription: d\n---\n# Heading\n\nbody" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);
    expect(screen.getByRole("heading", { name: "Heading" })).toBeInTheDocument();
    // The front matter is a key / value block above the title.
    const meta = screen.getByTestId("markdown-frontmatter");
    expect(meta).toHaveTextContent("description");
    expect(meta).toHaveTextContent("d");
    expect(screen.getByText("demo/SKILL.md")).toBeInTheDocument();
    expect(screen.getByText("2.3 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open in editor/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /wrap lines/i })).not.toBeInTheDocument();
  });

  test("a code file shows a wrap toggle and Edit, with no Open in editor", () => {
    stubContent({ path: "scripts/search.py", content: "print(1)" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="scripts/search.py" />);
    expect(screen.getByText("demo/scripts/search.py")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^edit$/i })).toBeInTheDocument();
    const wrap = screen.getByRole("button", { name: /wrap lines/i });
    expect(wrap).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(wrap);
    expect(wrap).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: /open in editor/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview" })).not.toBeInTheDocument();
  });

  test("a binary file says it can't be previewed and offers Reveal in Finder only", () => {
    stubContent({ path: "flow.png", binary: true, size: 49152 });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="flow.png" />);
    expect(screen.getByText("Can’t preview binary file")).toBeInTheDocument();
    expect(screen.getByText("flow.png · 48 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reveal in finder/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open in default app/i })).not.toBeInTheDocument();
  });

  test("editing and saving sends the content with the fingerprint it read", async () => {
    stubContent({ content: "old", fingerprint: "fp-1" });
    writeMock.mockResolvedValue({ fingerprint: "fp-2" } as never);
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);

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
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "typed" } });
    fireEvent.keyDown(box, { key: "s", metaKey: true });
    await vi.waitFor(() => expect(writeMock).toHaveBeenCalledTimes(1));
  });

  test("Cancel over a changed file asks before dropping the edit", () => {
    stubContent({ content: "old" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "typed" } });
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    const dialog = screen.getByRole("dialog", { name: "Discard your edit to SKILL.md?" });
    expect(dialog).toHaveTextContent(/agents keep the saved version/i);
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.getByRole("textbox")).toHaveValue("typed");
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    fireEvent.click(screen.getByRole("button", { name: "Discard edit" }));
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  test("Cancel over an unchanged file leaves editing without asking", () => {
    stubContent({ content: "old" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  async function refuseSave() {
    stubContent({ content: "old", fingerprint: "fp-1" });
    writeMock.mockRejectedValueOnce(new ApiError("SKILL_FILE_STALE", "changed on disk"));
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "my work" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await vi.waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/changed on disk after you opened it/i),
    );
  }

  acceptance(
    "web-ui",
    "a skill file changed on disk refuses the save and keeps the text",
    async () => {
      await refuseSave();
      expect(screen.getByText("Not saved")).toBeInTheDocument();
      expect(screen.getByRole("textbox")).toHaveValue("my work");
      // Compare… and Copy my text; there is no Reload — taking the disk's version is a choice in the dialog.
      for (const name of ["Compare…", "Copy my text"]) {
        expect(screen.getByRole("button", { name })).toBeInTheDocument();
      }
      expect(screen.queryByRole("button", { name: "Reload" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
    },
  );

  test("Compare… opens the two-way choice; Keep my edit saves over the file it just read", async () => {
    const mutate = vi.fn((_vars, opts) =>
      opts.onSuccess({ content: "disk text", fingerprint: "fp-disk" }),
    );
    readNowMock.mockReturnValue({ mutate, isPending: false } as never);
    await refuseSave();
    writeMock.mockResolvedValue({ fingerprint: "fp-3" } as never);
    fireEvent.click(screen.getByRole("button", { name: "Compare…" }));
    const dialog = await screen.findByRole("dialog", { name: "SKILL.md changed on both sides" });
    // Keep my edit is the first card and the chosen one.
    expect(within(dialog).getByRole("radio", { name: /Keep my edit/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(within(dialog).getByText("disk text")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save my edit" }));
    await vi.waitFor(() =>
      expect(writeMock).toHaveBeenLastCalledWith(SKILL_UID, {
        path: "SKILL.md",
        content: "my work",
        expected_fingerprint: "fp-disk",
      }),
    );
  });

  test("Compare… → Take the version on disk reloads and drops the edit, writing nothing", async () => {
    const mutate = vi.fn((_vars, opts) =>
      opts.onSuccess({ content: "disk text", fingerprint: "fp-disk" }),
    );
    readNowMock.mockReturnValue({ mutate, isPending: false } as never);
    await refuseSave();
    writeMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Compare…" }));
    const dialog = await screen.findByRole("dialog", { name: "SKILL.md changed on both sides" });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Take the version on disk/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Use the version on disk" }));
    await vi.waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument());
    expect(writeMock).not.toHaveBeenCalled();
  });

  test("a truncated file shows its start under a grey bar, read-only, with Open in editor", () => {
    stubContent({ path: "big.jsonl", content: "aaa", truncated: true, size: 18_000_000 });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="big.jsonl" />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Showing the first 3 B of 17.2 MB/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open in editor/i })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // spec skill-manager "Regenerate Coffer's builtin skill from the build": the
  // viewer offers no Edit.
  test("a builtin skill's files are read-only", () => {
    stubContent({ content: "# Guide" });
    renderViewer(<SkillFileViewer uid={SKILL_UID} owner="demo" path="SKILL.md" builtin />);
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
