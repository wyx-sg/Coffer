// src/components/skills/SkillReview.test.tsx — handing a review of skills to an agent.
//
// The Requires tab tells a skill that never declared what it needs ("unknown")
// from one that declared nothing, and carries the review hand-off in both
// states; the Skills selection bar reviews the ticked skills in one prompt.
// The prompt is asked of the daemon when a verb is picked. Real
// QueryClientProvider and toast; the api modules are mocked.
import { afterEach, beforeEach, describe, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { acceptance } from "@/test/acceptance";
import { ToastProvider } from "@/components/ui/toast";
import "@/i18n";
import type { SkillOut } from "@/lib/api/skills";
import { makeSkill } from "@/test/skillsPageKit";

import { SkillRequiresTab } from "./SkillRequiresTab";
import { SkillsBulkBar } from "./SkillsBulkBar";

vi.mock("@/lib/api/clis", () => ({
  clisApi: { list: vi.fn().mockResolvedValue({ items: [], warnings: [] }), checkAll: vi.fn() },
}));
vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: { reviewHandoff: vi.fn() },
}));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: {
    list: vi.fn().mockResolvedValue({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    }),
  },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    listTerminals: vi.fn().mockResolvedValue([{ label: "iTerm", value: "iterm" }]),
    openTerminal: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock("@/components/reach/BulkReachActions", () => ({ BulkReachActions: () => null }));
vi.mock("@/components/skills/SkillBulkDelete", () => ({ SkillBulkDelete: () => null }));
const { skillsApi } = await import("@/lib/api/skills");
const { fsApi } = await import("@/lib/api/fs");
const review = vi.mocked(skillsApi.reviewHandoff);

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const tab = (more: Partial<SkillOut>) =>
  wrap(
    <SkillRequiresTab
      skill={makeSkill({ uid: "sk-a", name: "a", requires: [], requires_declared: false, ...more })}
    />,
  );

beforeEach(() => review.mockResolvedValue({ prompt: "REVIEW PROMPT" }));
afterEach(() => vi.clearAllMocks());

describe("reviewing skills with an agent", () => {
  acceptance(
    "web-ui",
    "the requires tab says a skill that declared nothing is unknown",
    async () => {
      tab({});
      expect(await screen.findByText("What this skill needs is unknown")).toBeInTheDocument();
      expect(
        screen.getByText(/doesn’t declare what it needs, so Coffer doesn’t know/),
      ).toBeVisible();
      expect(screen.queryByText("Nothing required")).toBeNull();
      fireEvent.click(await screen.findByRole("button", { name: "Add requires with Claude Code" }));
      await waitFor(() => expect(review).toHaveBeenCalledWith(["sk-a"]));
      await waitFor(() =>
        expect(vi.mocked(fsApi.openTerminal)).toHaveBeenCalledWith(
          expect.objectContaining({ prompt: "REVIEW PROMPT" }),
        ),
      );
    },
  );

  acceptance("web-ui", "the requires tab offers a check to a skill that declared", async () => {
    tab({ requires_declared: true });
    expect(await screen.findByText("Nothing required")).toBeInTheDocument();
    expect(screen.queryByText("What this skill needs is unknown")).toBeNull();
    expect(
      await screen.findByRole("button", { name: "Check with Claude Code" }),
    ).toBeInTheDocument();
  });

  acceptance(
    "web-ui",
    "the skills selection bar checks the selected skills with one prompt",
    async () => {
      const skills = [
        makeSkill({ uid: "sk-1", name: "one" }),
        makeSkill({ uid: "sk-2", name: "two" }),
      ];
      wrap(<SkillsBulkBar skills={skills} total={5} onDone={vi.fn()} />);
      fireEvent.click(await screen.findByRole("button", { name: "Check with Claude Code" }));
      await waitFor(() => expect(review).toHaveBeenCalledWith(["sk-1", "sk-2"]));
    },
  );

  it("names the agent the review goes to and says what it does beside a lone button", async () => {
    tab({
      requires_declared: true,
      requires: [{ command: "jq", min_version: null, profiles: [] }],
    });
    expect(await screen.findByRole("button", { name: "Check with Claude Code" })).toBeVisible();
    expect(
      screen.getByText(/Claude Code reads this skill and suggests what to declare/),
    ).toBeVisible();
  });
});
