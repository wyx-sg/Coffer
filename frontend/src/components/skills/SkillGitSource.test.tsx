// src/components/skills/SkillGitSource.test.tsx
// The Source block of a Git-imported skill: pinned commit, status, Check now, and the update banner.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { SkillOut } from "@/lib/api/skills";
import { SkillGitSourcePanel } from "./SkillGitSource";
import { gitSkill, updatePreview } from "./skillSourceTestData";

vi.mock("@/lib/api/skills", () => ({
  skillsApi: {
    checkSource: vi.fn(),
    previewUpdate: vi.fn(),
    cancelStage: vi.fn(),
    applyUpdate: vi.fn(),
    keepMine: vi.fn(),
    compareUpdate: vi.fn(),
  },
}));
const { skillsApi } = await import("@/lib/api/skills");
const api = vi.mocked(skillsApi);

function renderPanel(skill: SkillOut) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SkillGitSourcePanel skill={skill} />
    </QueryClientProvider>,
  );
}

describe("SkillGitSourcePanel", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders nothing for a skill not imported from Git", () => {
    const skill = { ...gitSkill(), source: { type: "local_import", original_path: "/x" } };
    const { container } = renderPanel(skill as SkillOut);
    expect(container).toBeEmptyDOMElement();
  });

  test("shows the repository, folder, pinned commit and ref, and up to date", () => {
    renderPanel(gitSkill());
    expect(screen.getByText("https://github.com/acme/agent-skills")).toBeInTheDocument();
    expect(screen.getByText("terraform-plan")).toBeInTheDocument();
    expect(screen.getByText("a1b2c3d")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("Up to date")).toBeInTheDocument();
  });

  test("says when the source was never checked", () => {
    renderPanel(gitSkill(null));
    expect(screen.getByText("Not checked yet")).toBeInTheDocument();
  });

  test("Check now checks the source", async () => {
    api.checkSource.mockResolvedValue(gitSkill().source_status!);
    renderPanel(gitSkill());
    fireEvent.click(screen.getByRole("button", { name: "Check now" }));
    await waitFor(() => expect(api.checkSource).toHaveBeenCalledWith("sk-1"));
  });

  test("an available update shows the banner with its range, and Review opens the preview", async () => {
    api.previewUpdate.mockResolvedValue(updatePreview());
    renderPanel(
      gitSkill({
        update_available: true,
        latest_commit: "f9e8d7c6b5a4",
        commits_ahead: 3,
        files_changed: 2,
      }),
    );
    expect(
      screen.getByText("An update is available from github.com/acme/agent-skills"),
    ).toBeInTheDocument();
    expect(screen.getByText(/main moved 3 commits past the pinned a1b2c3d/)).toBeInTheDocument();
    expect(screen.getByText("Update available")).toBeInTheDocument();
    expect(screen.getByText("f9e8d7c")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review update…" }));
    await waitFor(() => expect(api.previewUpdate).toHaveBeenCalledWith("sk-1"));
    expect(
      await screen.findByRole("dialog", { name: "Update terraform-plan" }),
    ).toBeInTheDocument();
  });

  test("an unreachable source shows git's message and the last successful check", () => {
    renderPanel(
      gitSkill({
        error: "fatal: repository not found",
        checked_at: "2026-09-30T09:12:00Z",
        last_success_at: "2026-09-29T08:00:00Z",
      }),
    );
    expect(screen.getByText("Can't reach github.com/acme/agent-skills")).toBeInTheDocument();
    expect(screen.getByText("fatal: repository not found")).toBeInTheDocument();
    expect(screen.getByText(/^Last successful check: /)).toBeInTheDocument();
    expect(screen.getByText(/^Source unreachable since /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });
});
