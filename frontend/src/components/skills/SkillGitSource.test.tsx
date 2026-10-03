// src/components/skills/SkillGitSource.test.tsx
// The Source bar of a Git-imported skill (canvas 4.3.17, 4.3.21): one line —
// the pinned commit on its branch and the day, when it was last checked, Check
// again and Change source…; the update and unreachable banners above the tabs
// are SkillBanners'.
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

  test("is one line: the pinned commit on its branch, when it was checked, and two actions", () => {
    renderPanel(gitSkill());
    const bar = screen.getByTestId("skill-source-bar");
    expect(bar).toHaveTextContent(/Pinned a1b2c3d on main/);
    expect(screen.getByText("a1b2c3d")).toHaveClass("font-mono");
    expect(screen.getByText("main")).toHaveClass("font-mono");
    expect(bar).toHaveTextContent(/Checked at \d\d:\d\d/);
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change source…" })).toBeInTheDocument();
    // The old four-row block is gone.
    expect(screen.queryByText("Repository")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check now" })).not.toBeInTheDocument();
  });

  test("a skill never checked shows no 'Checked at'", () => {
    renderPanel(gitSkill(null));
    expect(screen.queryByText(/Checked at/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });

  test("Check again checks the source", async () => {
    api.checkSource.mockResolvedValue(gitSkill().source_status!);
    renderPanel(gitSkill());
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(api.checkSource).toHaveBeenCalledWith("sk-1"));
  });

  test("an unreachable source hides Check again and 'Checked at' — the banner carries them", () => {
    renderPanel(gitSkill({ error: "repository not found" }));
    expect(screen.queryByRole("button", { name: "Check again" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Checked at/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change source…" })).toBeInTheDocument();
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
      // The branch and folder fields say what an empty value means.
      expect(dialog).toHaveTextContent("Leave empty for the default branch.");
      expect(dialog).toHaveTextContent("Leave empty when it is at the top.");
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
      // The review is the 1060 change preview with the primary naming the write.
      expect(await screen.findByRole("button", { name: /^Change to / })).toBeInTheDocument();
      expect(screen.getByText("What will happen")).toBeInTheDocument();
      expect(api.applyUpdate).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
      await waitFor(() => expect(api.cancelStage).toHaveBeenCalled());
    },
  );
});
