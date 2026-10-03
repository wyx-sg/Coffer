// src/components/skills/SkillAddDialog.test.tsx
// The Add skill dialog: three sources and no create; a stage is looked at, chosen from and confirmed, and cancelled on every other way out.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import type { SkillStaging, StagedSkill } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { SkillAddDialog } from "./SkillAddDialog";

vi.mock("@/lib/api/skills", () => ({
  skillsApi: {
    stageFolder: vi.fn(),
    stageArchive: vi.fn(),
    stageGit: vi.fn(),
    confirmStage: vi.fn(),
    cancelStage: vi.fn(),
  },
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("@/lib/api/fs", () => ({ fsApi: { browse: vi.fn(), pickFolder: vi.fn() } }));
vi.mock("@/lib/api/resources", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/resources")>()),
  resourcesApi: { disable: vi.fn(async () => undefined), enable: vi.fn(async () => undefined) },
}));

const { skillsApi } = await import("@/lib/api/skills");
const api = vi.mocked(skillsApi);

function staged(over: Partial<StagedSkill> = {}): StagedSkill {
  return {
    folder: ".",
    name: "release-notes",
    description: "Draft release notes.",
    file_count: 4,
    size_bytes: 18_000,
    valid: true,
    reason: null,
    message: null,
    taken: false,
    protected: false,
    ...over,
  };
}

function stage(skills: StagedSkill[], kind: SkillStaging["kind"] = "archive"): SkillStaging {
  return {
    staging_id: "stg-1",
    kind,
    label: "skills.zip",
    ref: null,
    subpath: "",
    commit: null,
    skills,
  };
}

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderDialog(props: Partial<Parameters<typeof SkillAddDialog>[0]> = {}) {
  const onOpenChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/skills"]}>
          <Routes>
            <Route
              path="*"
              element={
                <>
                  <SkillAddDialog open onOpenChange={onOpenChange} {...props} />
                  <Where />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

const zip = () => new File(["PK"], "skills.zip", { type: "application/zip" });

function uploadArchive() {
  fireEvent.click(screen.getByRole("radio", { name: "From an archive" }));
  fireEvent.change(screen.getByLabelText("Archive"), { target: { files: [zip()] } });
}

describe("SkillAddDialog", () => {
  // Unmounting a dialog with a stage open cancels it asynchronously, so the
  // previous test's cancel lands after its own teardown: clear before each test.
  beforeEach(() => vi.clearAllMocks());

  acceptance("skill-manager", "the add dialog offers three sources and no create", () => {
    renderDialog();
    const sources = screen.getAllByRole("radio").map((r) => r.textContent);
    expect(sources).toEqual(["From a folder", "From an archive", "From Git"]);
    expect(screen.queryByText(/create|new skill|from scratch/i)).not.toBeInTheDocument();
  });

  acceptance("skill-manager", "nothing is added until the user confirms", async () => {
    api.stageArchive.mockResolvedValue(stage([staged()]));
    api.cancelStage.mockResolvedValue(undefined);
    const { onOpenChange } = renderDialog();
    uploadArchive();
    expect(await screen.findByText("Found SKILL.md at the top level")).toBeInTheDocument();
    expect(api.stageArchive).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(api.cancelStage).toHaveBeenCalledWith("stg-1"));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.confirmStage).not.toHaveBeenCalled();
  });

  test("opens on the source it is given", () => {
    renderDialog({ initialSource: "git" });
    expect(screen.getByRole("radio", { name: "From Git" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText("Repository URL")).toBeInTheDocument();
  });

  test("switching source cancels the open stage", async () => {
    api.stageArchive.mockResolvedValue(stage([staged()]));
    renderDialog();
    uploadArchive();
    await screen.findByText("Found SKILL.md at the top level");
    fireEvent.click(screen.getByRole("radio", { name: "From Git" }));
    await waitFor(() => expect(api.cancelStage).toHaveBeenCalledWith("stg-1"));
  });

  test("a pasted folder path is trimmed of quotes and staged", async () => {
    api.stageFolder.mockResolvedValue(stage([staged()], "folder"));
    renderDialog();
    fireEvent.change(screen.getByLabelText("Folder"), {
      target: { value: '  "/Users/me/skills/release-notes"\n' },
    });
    await waitFor(() =>
      expect(api.stageFolder).toHaveBeenCalledWith("/Users/me/skills/release-notes"),
    );
    expect(await screen.findByText("release-notes")).toBeInTheDocument();
  });

  test("several skills: choosing two confirms exactly those, then opens the first", async () => {
    api.stageArchive.mockResolvedValue(
      stage([
        staged({ folder: "release", name: "release" }),
        staged({ folder: "review", name: "review" }),
        staged({ folder: "triage", name: "triage" }),
      ]),
    );
    api.confirmStage.mockResolvedValue({
      items: [{ name: "review" }, { name: "triage" }],
    } as never);
    const { onOpenChange } = renderDialog();
    uploadArchive();
    await screen.findByText("3 skills found — pick which to add");

    const add = screen.getByRole("button", { name: "Add skill" });
    expect(add).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Add review" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Add triage" }));
    fireEvent.click(screen.getByRole("button", { name: "Add 2 skills" }));

    await waitFor(() =>
      expect(api.confirmStage).toHaveBeenCalledWith("stg-1", {
        skills: ["review", "triage"],
        replace: [],
      }),
    );
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(api.cancelStage).not.toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("/skills/review");
  });

  test("a taken name is replaced only when chosen as Replace", async () => {
    api.stageArchive.mockResolvedValue(
      stage([
        staged({ folder: "review", name: "review", taken: true }),
        staged({ folder: "triage", name: "triage" }),
      ]),
    );
    api.confirmStage.mockResolvedValue({ items: [{ name: "review" }] } as never);
    renderDialog();
    uploadArchive();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Replace review" }));
    fireEvent.click(screen.getByRole("button", { name: "Add skill" }));
    await waitFor(() =>
      expect(api.confirmStage).toHaveBeenCalledWith("stg-1", {
        skills: ["review"],
        replace: ["review"],
      }),
    );
  });

  test("a single taken skill asks to replace it by name", async () => {
    api.stageArchive.mockResolvedValue(stage([staged({ name: "pdf", taken: true })]));
    api.confirmStage.mockResolvedValue({ items: [{ name: "pdf" }] } as never);
    renderDialog();
    uploadArchive();
    expect(await screen.findByText("You already have a skill named pdf")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replace pdf" }));
    await waitFor(() =>
      expect(api.confirmStage).toHaveBeenCalledWith("stg-1", {
        skills: ["pdf"],
        replace: ["pdf"],
      }),
    );
  });

  test("an invalid or built-in skill cannot be chosen, and says why", async () => {
    api.stageArchive.mockResolvedValue(
      stage([
        staged({
          folder: "broken",
          name: null,
          valid: false,
          reason: "skill_md_missing",
          message: "SKILL.md has no frontmatter",
        }),
        staged({ folder: "coffer-guide", name: "coffer-guide", taken: true, protected: true }),
        staged({ folder: "ok", name: "ok" }),
      ]),
    );
    renderDialog();
    uploadArchive();
    expect(await screen.findByText("SKILL.md has no frontmatter")).toBeInTheDocument();
    expect(screen.getByText(/built-in skill has this name/)).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
  });

  test("an unsafe archive lists the offending entries", async () => {
    api.stageArchive.mockRejectedValue(
      new ApiError("SKILL_INVALID", "the archive holds unsafe entries", {
        reason: "archive_unsafe_entries",
        offenders: [
          { entry: "../evil.sh", problem: "parent_segment" },
          { entry: "link", problem: "symlink" },
        ],
      }),
    );
    renderDialog();
    uploadArchive();
    expect(await screen.findByText(/Nothing was unpacked/)).toBeInTheDocument();
    expect(screen.getByText("../evil.sh")).toBeInTheDocument();
    expect(screen.getByText("symbolic link")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add skill" })).toBeDisabled();
  });

  test("an archive with no SKILL.md says where one must be", async () => {
    api.stageArchive.mockRejectedValue(
      new ApiError("SKILL_INVALID", "no SKILL.md", {
        reason: "skill_md_not_found",
        looked_in: ["skills.zip/SKILL.md"],
      }),
    );
    renderDialog();
    uploadArchive();
    expect(
      await screen.findByText(
        "No SKILL.md in skills.zip. Coffer looks at the top level and one folder down.",
      ),
    ).toBeInTheDocument();
    // The drop zone already has Choose file…, so no second button offers another file.
    expect(screen.queryByRole("button", { name: "Choose another file" })).not.toBeInTheDocument();
  });

  test("a folder whose skill is one level down offers to use that folder", async () => {
    api.stageFolder
      .mockRejectedValueOnce(
        new ApiError("SKILL_INVALID", "scripts/latest links outside the folder", {
          reason: "symlink",
          candidate_folder: "skill",
          candidate_path: "/Users/me/changelog-main/skill",
        }),
      )
      .mockResolvedValueOnce(stage([staged()], "folder"));
    renderDialog();
    fireEvent.change(screen.getByLabelText("Folder"), {
      target: { value: "/Users/me/changelog-main" },
    });
    fireEvent.blur(screen.getByLabelText("Folder"));
    expect(await screen.findByText("skill/")).toBeInTheDocument();
    expect(screen.getByText("scripts/latest links outside the folder")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add skill" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Use that folder" }));
    await waitFor(() =>
      expect(api.stageFolder).toHaveBeenLastCalledWith("/Users/me/changelog-main/skill"),
    );
    expect(await screen.findByText("Valid skill folder")).toBeInTheDocument();
  });

  test("a Git source names the pinned branch and commit", async () => {
    api.stageGit.mockResolvedValue({
      ...stage([staged({ name: "pdf" })], "git"),
      ref: "main",
      commit: "3f9c2a1b8d0e",
      subpath: "pdf",
    });
    renderDialog({ initialSource: "git" });
    fireEvent.change(screen.getByLabelText("Repository URL"), { target: { value: "https://x/y" } });
    fireEvent.click(screen.getByRole("button", { name: "Clone" }));
    expect(await screen.findByText("Found SKILL.md in pdf/")).toBeInTheDocument();
    expect(screen.getByText("main · 3f9c2a1")).toBeInTheDocument();
  });

  test("a Git name conflict offers Replace or Cancel, with no rename", async () => {
    api.stageGit.mockResolvedValue(stage([staged({ name: "pdf", taken: true })], "git"));
    renderDialog({ initialSource: "git" });
    fireEvent.change(screen.getByLabelText("Repository URL"), { target: { value: "https://x/y" } });
    fireEvent.click(screen.getByRole("button", { name: "Clone" }));
    expect(await screen.findByText("You already have a skill named pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace pdf" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByText(/rename/i)).not.toBeInTheDocument();
  });

  test("Available to defaults to all agents and writes nothing extra", async () => {
    const { resourcesApi } = await import("@/lib/api/resources");
    api.stageArchive.mockResolvedValue(stage([staged({ folder: ".", name: "changelog" })]));
    api.confirmStage.mockResolvedValue({
      items: [{ uid: "sk-new", name: "changelog" }],
    } as never);
    renderDialog();
    uploadArchive();
    await screen.findByText("Found SKILL.md at the top level");
    expect(screen.getByText("Available to", { selector: "label" })).toBeInTheDocument();
    expect(within(screen.getByTestId("skill-add-reach")).getByRole("button")).toHaveTextContent(
      "All agents",
    );
    fireEvent.click(screen.getByRole("button", { name: "Add skill" }));
    await waitFor(() => expect(api.confirmStage).toHaveBeenCalled());
    expect(vi.mocked(resourcesApi.disable)).not.toHaveBeenCalled();
  });

  test("a failed clone is a problem block with the hand-off, and Retry", async () => {
    const prompt = "Find out why git cannot clone https://x/y.";
    api.stageGit
      .mockRejectedValueOnce(
        new ApiError(
          "SKILL_SOURCE_UNREACHABLE",
          "git clone failed: fatal: Could not resolve host: x",
          {
            handoff: { prompt },
          },
        ),
      )
      .mockResolvedValueOnce(stage([staged()], "git"));
    renderDialog({ initialSource: "git" });
    fireEvent.change(screen.getByLabelText("Repository URL"), { target: { value: "https://x/y" } });
    fireEvent.change(screen.getByLabelText("Branch or tag"), { target: { value: "main" } });
    fireEvent.click(screen.getByRole("button", { name: "Clone" }));
    await waitFor(() => expect(api.stageGit).toHaveBeenCalled());
    expect(api.stageGit).toHaveBeenCalledWith({ url: "https://x/y", ref: "main", path: null });
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Couldn't clone y")).toBeInTheDocument();
    expect(within(alert).getByText("Could not resolve host: x")).toBeInTheDocument();
    expect(within(alert).getByText(/or hand it to an agent/)).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Found SKILL.md at the top level")).toBeInTheDocument();
  });

  acceptance(
    "skill-manager",
    "a skill import with no git hands installing it to an agent",
    async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
      const prompt = "Install git on this machine. This machine: macOS 15.6, arm64.";
      api.stageGit.mockRejectedValueOnce(
        new ApiError("SKILL_SOURCE_UNREACHABLE", "git is not installed on this machine", {
          reason: "git_missing",
          handoff: { prompt },
        }),
      );
      renderDialog({ initialSource: "git" });
      fireEvent.change(screen.getByLabelText("Repository URL"), {
        target: { value: "https://x/y" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Clone" }));
      const alert = await screen.findByRole("alert");
      fireEvent.click(within(alert).getByRole("button", { name: "Copy prompt" }));
      expect(writeText).toHaveBeenCalledWith(prompt);
    },
  );
});
