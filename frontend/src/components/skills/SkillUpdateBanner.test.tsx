// frontend/src/components/skills/SkillUpdateBanner.test.tsx
// A Git skill's update is a hand-off, not something Coffer applies (spec
// skill-manager "Hand a Git-imported skill's update to an agent"): the one
// primary action is the hand-off split button with I merged it beside it, and
// the change is looked at in the editor or on the source's host.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { ToastProvider } from "@/components/ui/toast";
import type { SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { SkillBanners } from "./SkillBanners";
import { gitSkill, updatableSkill } from "./skillSourceTestData";

vi.mock("@/lib/api/skills", () => ({
  skillsApi: { checkSource: vi.fn(), updateHandoff: vi.fn(), recordMerged: vi.fn() },
}));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
vi.mock("@/lib/api/fs", () => ({
  fsApi: { listTerminals: vi.fn(), openTerminal: vi.fn(), open: vi.fn() },
}));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
const { skillsApi } = await import("@/lib/api/skills");
const { agentProvidersApi } = await import("@/lib/api/agentProviders");
const { fsApi } = await import("@/lib/api/fs");
const api = vi.mocked(skillsApi);
const fs = vi.mocked(fsApi);

const PROMPT = "Skill terraform-plan's source has an update.";

function renderBanners(skill: SkillOut, attention: "update" | "none" = "update") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <SkillBanners
            skill={skill}
            items={attention === "update" ? [{ kind: "updateAvailable" }] : []}
            onReviewCopy={vi.fn()}
          />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("SkillUpdateBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(agentProvidersApi.list).mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    } as never);
    fs.listTerminals.mockResolvedValue([{ label: "iTerm", value: "iterm" }]);
    fs.openTerminal.mockResolvedValue(undefined as never);
    fs.open.mockResolvedValue(undefined as never);
    api.updateHandoff.mockResolvedValue({ commit: "f9e8d7c6b5a4", handoff: { prompt: PROMPT } });
  });

  acceptance(
    "skill-manager",
    "the update is offered only as a hand-off while an update is available",
    async () => {
      const { unmount } = renderBanners(updatableSkill());
      const banner = screen.getByTestId("skill-banner-update");
      const handoff = await within(banner).findByRole("button", {
        name: "Hand off to Claude Code to update",
      });
      expect(within(banner).getByRole("button", { name: "I merged it" })).toBeInTheDocument();
      for (const gone of [/Review update/, /Apply/, /Keep mine/, /Take theirs/, /Compare/]) {
        expect(within(banner).queryByRole("button", { name: gone })).not.toBeInTheDocument();
      }
      // The prompt is fetched when the verb is picked, and goes to the agent's terminal.
      expect(api.updateHandoff).not.toHaveBeenCalled();
      fireEvent.click(handoff);
      await waitFor(() => expect(api.updateHandoff).toHaveBeenCalledWith("sk-1"));
      await waitFor(() =>
        expect(fs.openTerminal).toHaveBeenCalledWith(
          expect.objectContaining({ agent: "claude_code", prompt: PROMPT }),
        ),
      );
      unmount();

      // Up to date: no update attention, so neither action is offered.
      renderBanners(gitSkill(), "none");
      expect(screen.queryByTestId("skill-banner-update")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /to update/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "I merged it" })).not.toBeInTheDocument();
    },
  );

  test("I merged it asks first, then records the update's commit", async () => {
    api.recordMerged.mockResolvedValue(updatableSkill());
    renderBanners(updatableSkill());
    fireEvent.click(screen.getByRole("button", { name: "I merged it" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Record terraform-plan as merged?");
    expect(api.recordMerged).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "I merged it" }));
    await waitFor(() => expect(api.recordMerged).toHaveBeenCalledWith("sk-1", "f9e8d7c6b5a4"));
  });

  acceptance(
    "skill-manager",
    "an update is looked at in the editor or on the source's host",
    async () => {
      const github = updatableSkill();
      const { unmount } = renderBanners(github);
      const banner = screen.getByTestId("skill-banner-update");
      fireEvent.click(within(banner).getByRole("button", { name: "Open in editor" }));
      await waitFor(() => expect(fs.open).toHaveBeenCalledWith(github.master_path, undefined));
      const link = within(banner).getByRole("link", { name: "View upstream changes" });
      expect(link).toHaveAttribute(
        "href",
        "https://github.com/acme/agent-skills/compare/a1b2c3d4e5f6...f9e8d7c6b5a4",
      );
      expect(screen.queryByTestId("skill-update-range")).not.toBeInTheDocument();
      unmount();

      // A self-hosted repository: no link, the copyable range and the commits' subjects.
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
      renderBanners(updatableSkill({ compare_url: null }));
      const own = screen.getByTestId("skill-banner-update");
      expect(within(own).queryByRole("link")).not.toBeInTheDocument();
      expect(within(own).getByRole("button", { name: "Open in editor" })).toBeInTheDocument();
      const range = screen.getByTestId("skill-update-range");
      expect(range).toHaveTextContent("a1b2c3d..f9e8d7c");
      expect(range).toHaveTextContent("Ask before backend changes");
      expect(range).toHaveTextContent("Add plan.sh");
      fireEvent.click(within(range).getByRole("button", { name: "Copy the commit range" }));
      await waitFor(() => expect(writeText).toHaveBeenCalledWith("a1b2c3d..f9e8d7c"));
      // Neither draws a diff.
      expect(within(own).queryByTestId("file-diff")).not.toBeInTheDocument();
    },
  );
});
