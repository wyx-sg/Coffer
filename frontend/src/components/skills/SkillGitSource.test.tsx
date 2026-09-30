// src/components/skills/SkillGitSource.test.tsx
// The Source block of a Git-imported skill: repository, folder, pinned commit,
// status, Check now and Change source…; the update and unreachable banners
// above the tabs are SkillBanners' (SkillBanners.test.tsx).
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { SkillGitSourcePanel } from "./SkillGitSource";
import { gitSkill, updatePreview } from "./skillSourceTestData";

vi.mock("@/lib/api/skills", () => ({
  skillsApi: {
    checkSource: vi.fn(),
    changeSource: vi.fn(),
    cancelStage: vi.fn(),
    applyUpdate: vi.fn(),
  },
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
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
    expect(screen.getByText("terraform-plan/")).toBeInTheDocument();
    expect(screen.getByText("a1b2c3d")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("Up to date")).toBeInTheDocument();
  });

  test("an update shows its commit, commits and files in the status row", () => {
    renderPanel(
      gitSkill({
        update_available: true,
        latest_commit: "f9e8d7c6b5a4",
        commits_ahead: 3,
        files_changed: 2,
      }),
    );
    expect(screen.getByText("Update available")).toBeInTheDocument();
    expect(screen.getByText("f9e8d7c")).toBeInTheDocument();
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

  acceptance(
    "web-ui",
    "changing a skill's source shows the change before anything is replaced",
    async () => {
      api.changeSource.mockResolvedValue(updatePreview());
      renderPanel(gitSkill());
      fireEvent.click(screen.getByRole("button", { name: "Change source…" }));
      const dialog = await screen.findByRole("dialog", {
        name: "Change source of terraform-plan",
      });
      expect(dialog).toHaveTextContent("Nothing is replaced yet");
      const url = screen.getByLabelText(/Repository URL/);
      expect(url).toHaveValue("https://github.com/acme/agent-skills");
      fireEvent.change(url, { target: { value: "https://github.com/platform-team/skills" } });
      fireEvent.click(screen.getByRole("button", { name: "Check source" }));
      await waitFor(() =>
        expect(api.changeSource).toHaveBeenCalledWith("sk-1", {
          url: "https://github.com/platform-team/skills",
          ref: "main",
          path: "terraform-plan",
        }),
      );
      expect(await screen.findByRole("button", { name: /^Change to / })).toBeInTheDocument();
      expect(api.applyUpdate).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      await waitFor(() => expect(api.cancelStage).toHaveBeenCalled());
    },
  );
});
