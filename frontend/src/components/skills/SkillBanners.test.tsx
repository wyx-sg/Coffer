// frontend/src/components/skills/SkillBanners.test.tsx
// The banners above an open skill's tabs: an update waiting (Review update…, an
// outline button) and a Git source that can't be reached — Check again, then
// the Ask an agent ▾ split button and its "?", because a network, VPN or
// credential problem is on this machine; the hand-off prompt names the
// repository and git's own error.
import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { SkillBanners } from "./SkillBanners";
import { gitSkill } from "./skillSourceTestData";

vi.mock("@/lib/api/skills", () => ({ skillsApi: { checkSource: vi.fn() } }));
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn(() => ({ data: [] })) }));
const { skillsApi } = await import("@/lib/api/skills");
const api = vi.mocked(skillsApi);

function renderBanners(
  status: Parameters<typeof gitSkill>[0],
  items: Parameters<typeof SkillBanners>[0]["items"],
  onReviewUpdate = vi.fn(),
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SkillBanners
          skill={gitSkill(status)}
          items={items}
          onReviewCopy={vi.fn()}
          onReviewUpdate={onReviewUpdate}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onReviewUpdate };
}

describe("SkillBanners", () => {
  beforeEach(() => vi.clearAllMocks());

  test("an update waiting says what moved and offers Review update…", () => {
    const { onReviewUpdate } = renderBanners(
      { update_available: true, commits_ahead: 3, files_changed: 2 },
      [{ kind: "updateAvailable" }],
    );
    const banner = screen.getByTestId("skill-banner-update");
    expect(banner).toHaveTextContent("An update is available from github.com/acme/agent-skills");
    expect(banner).toHaveTextContent("main moved 3 commits past the pinned a1b2c3d");
    const review = within(banner).getByRole("button", { name: "Review update…" });
    fireEvent.click(review);
    expect(onReviewUpdate).toHaveBeenCalled();
  });

  test("an unreachable source: Check again, then the hand-off, then its ?", async () => {
    api.checkSource.mockResolvedValue(gitSkill().source_status!);
    renderBanners({ error: "repository not found" }, [{ kind: "sourceUnreachable" }]);
    const banner = screen.getByTestId("skill-banner-unreachable");
    expect(banner).toHaveTextContent("Can’t reach github.com/acme/agent-skills");
    expect(banner).toHaveTextContent("The skill keeps working from its pinned copy");
    const buttons = within(banner).getAllByRole("button");
    // Check again first; the hand-off follows (with no managed agent it is Copy prompt alone).
    expect(buttons[0]).toHaveTextContent("Check again");
    expect(buttons[1]).toHaveTextContent("Copy prompt");
    // …and the "?" that says why Coffer hands it off.
    expect(buttons).toHaveLength(3);
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(api.checkSource).toHaveBeenCalledWith("sk-1"));
  });

  test("the hand-off prompt names the repository, the skill and git's error", () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderBanners({ error: "repository not found" }, [{ kind: "sourceUnreachable" }]);
    fireEvent.click(
      within(screen.getByTestId("skill-banner-unreachable")).getByRole("button", {
        name: /copy prompt/i,
      }),
    );
    const prompt = writeText.mock.calls[0][0] as string;
    expect(prompt).toContain("https://github.com/acme/agent-skills");
    expect(prompt).toContain("repository not found");
    expect(prompt).toContain("terraform-plan");
  });
});
