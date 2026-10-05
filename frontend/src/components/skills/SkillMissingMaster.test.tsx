// A skill whose master folder is gone: the Files tab is an empty state that says
// there are no files to show, and the banner offers the hand-off that has an
// agent look for a copy to put back (Copy prompt, the prompt the drift report
// carries for this skill) and Delete skill…. Coffer restores nothing itself and
// the banner has no Restore from History.
import { expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { SkillMasterBanner } from "@/components/skills/SkillMasterBanner";
import { SkillMissingMaster } from "@/components/skills/SkillMissingMaster";
import { ToastProvider } from "@/components/ui/toast";
import "@/i18n";
import { makeSkill } from "@/test/skillsPageKit";

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: { verify: vi.fn(), remove: vi.fn() },
}));
vi.mock("@/lib/api/agentProviders", () => ({ agentProvidersApi: { list: vi.fn() } }));
const { skillsApi } = await import("@/lib/api/skills");
const { agentProvidersApi } = await import("@/lib/api/agentProviders");

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <SkillMasterBanner skill={makeSkill({ name: "hello" })} onDeleted={() => {}} />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const finding = (skill: string, kind: string, prompt: string | null) => ({
  skill_name: skill,
  agent_name: "",
  kind,
  target_path: `/vault/skills/${skill}`,
  handoff: prompt === null ? null : { prompt },
});

test("the banner copies the prompt that looks for a copy and offers Delete skill…", async () => {
  vi.mocked(agentProvidersApi.list).mockResolvedValue({ agents: [] } as never);
  vi.mocked(skillsApi.verify).mockResolvedValue({
    entries: [
      finding("other", "missing_master", "Look for other."),
      finding("hello", "missing_master", "Look for a copy of hello."),
    ],
  } as never);
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  mount();
  expect(screen.getByRole("button", { name: "Delete skill…" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Restore from History/ })).toBeNull();
  fireEvent.click(await screen.findByRole("button", { name: "Copy prompt" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("Look for a copy of hello."));
});

test("the Files tab explains the empty folder and offers no History", () => {
  render(<SkillMissingMaster />);
  expect(screen.getByText("No files to show")).toBeInTheDocument();
  expect(screen.queryByRole("button")).toBeNull();
});
