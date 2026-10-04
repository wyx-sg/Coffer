// src/components/agents/AgentSkillsTab.bulk.test.tsx — acting on several of the agent's own skills at once.
//
// Covered: a checkbox per own row and none on Coffer's part; the bar reading "N
// of M selected" in place of the search; Adopt acting on unmanaged folders only
// and saying how many it skips; one request per skill, in order, with the shared
// reach and each folder's name; a name Coffer already has failing that skill
// alone with Retry for just it; Delete…; Esc clearing; the search narrowing what
// select-all reaches. The hooks run for real against the mocked wire.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AgentSkillsTab } from "./AgentSkillsTab";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import type { UnmanagedSkillOut } from "@/lib/api/agents-workspace";
import { ApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    unmanagedSkills: vi.fn(),
    unmanagedSkillFiles: vi.fn(),
    adoptUnmanagedSkill: vi.fn(),
    deleteUnmanagedSkill: vi.fn(),
  },
}));
vi.mock("@/lib/api/skills", () => ({ skillsApi: { list: vi.fn() } }));

const { agentsApi } = await import("@/lib/api/agents");
const api = vi.mocked(agentsApi);
const { skillsApi } = await import("@/lib/api/skills");
const skillsList = vi.mocked(skillsApi.list);

const AGENT: AgentOut = {
  uid: "u-cc",
  name: "claude_code",
  type: "claude_code",
  config_dir: "/Users/me/.claude",
  display_name: "Claude Code",
  model: null,
  effort: null,
  tier_models: null,
  version: null,
  state: "installed_active",
  install_handoff: null,
  connection_uid: null,
  created_at: "",
  updated_at: "",
};

function own(name: string, extra: Partial<UnmanagedSkillOut> = {}): UnmanagedSkillOut {
  return {
    name,
    path: `/Users/me/.claude/skills/${name}`,
    location: "skills",
    valid: true,
    reason: null,
    foreign_link: false,
    ...extra,
  };
}

const DELIVERED = {
  uid: "s-pdf",
  name: "pdf",
  description: "",
  builtin: false,
  enabled: true,
  master_path: "/Users/me/.coffer/skills/pdf",
  bindings: [
    {
      agent_uid: "u-cc",
      agent_name: "claude_code",
      last_link_path: "/x",
      last_linked_at: null,
      link_mode: null,
    },
  ],
} as unknown as SkillOut;

const OWN = [own("alpha"), own("beta"), own("gamma"), own("pdf")];

function stub() {
  skillsList.mockResolvedValue({ items: [DELIVERED] } as Awaited<
    ReturnType<typeof skillsApi.list>
  >);
  api.unmanagedSkills.mockResolvedValue({ items: OWN });
  api.adoptUnmanagedSkill.mockResolvedValue({ uid: "s-new", name: "x" });
  api.deleteUnmanagedSkill.mockResolvedValue(undefined);
  api.unmanagedSkillFiles.mockResolvedValue({ root: undefined } as never);
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <AgentSkillsTab agent={AGENT} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const tick = (name: string) =>
  fireEvent.click(screen.getByRole("checkbox", { name: `Select ${name}` }));
const bar = () => screen.getByRole("region", { name: "Selected skills" });

afterEach(() => vi.clearAllMocks());

describe("AgentSkillsTab — bulk", () => {
  acceptance(
    "agent-registry",
    "adopt or delete several of the agent's own skills at once",
    async () => {
      stub();
      // The second adoption fails: Coffer already has a skill of that name.
      api.adoptUnmanagedSkill
        .mockResolvedValueOnce({ uid: "s-1", name: "alpha" })
        .mockRejectedValueOnce(new ApiError("SKILL_ALREADY_EXISTS", "name taken"))
        .mockResolvedValueOnce({ uid: "s-3", name: "gamma" });
      renderTab();
      await screen.findByRole("link", { name: "alpha" });
      for (const name of ["alpha", "beta", "gamma", "pdf"]) tick(name);
      expect(within(bar()).getByText("4 of 4 selected")).toBeInTheDocument();
      expect(screen.queryByLabelText("Search skills")).toBeNull();

      fireEvent.click(within(bar()).getByRole("button", { name: "Adopt" }));
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText("Adopt 3 skills?")).toBeInTheDocument();
      expect(
        within(dialog).getByText(/1 selected skill is skipped: only unmanaged folders/),
      ).toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole("button", { name: "Adopt 3 skills" }));

      // One failure never stops the others; the dialog names it and offers Retry.
      fireEvent.click(await within(dialog).findByRole("button", { name: "Retry 1 that failed" }));
      await waitFor(() => expect(api.adoptUnmanagedSkill).toHaveBeenCalledTimes(4));
      const reach = { mode: "everywhere", agents: [] };
      expect(api.adoptUnmanagedSkill.mock.calls.map((c) => c.slice(0, 3))).toEqual([
        ["u-cc", "alpha", "skills"],
        ["u-cc", "beta", "skills"],
        ["u-cc", "gamma", "skills"],
        ["u-cc", "beta", "skills"],
      ]);
      expect(api.adoptUnmanagedSkill.mock.calls[0]?.[3]).toEqual({ reach });
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(screen.getByText("Adopted 3 skills")).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Selected skills" })).toBeNull();
    },
  );

  test("the failed adoption is listed by name before it is retried", async () => {
    stub();
    api.adoptUnmanagedSkill.mockRejectedValueOnce(
      new ApiError("SKILL_ALREADY_EXISTS", "name taken"),
    );
    renderTab();
    await screen.findByRole("link", { name: "alpha" });
    tick("alpha");
    tick("beta");
    fireEvent.click(within(bar()).getByRole("button", { name: "Adopt" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt 2 skills" }));
    const alert = await within(dialog).findByRole("alert");
    expect(within(alert).getByText("Adopted 1 of 2")).toBeInTheDocument();
    expect(within(alert).getByText("alpha")).toBeInTheDocument();
    expect(api.adoptUnmanagedSkill).toHaveBeenCalledTimes(2);
  });

  test("Delete… deletes every ticked folder, one request each, after one confirmation", async () => {
    stub();
    renderTab();
    await screen.findByRole("link", { name: "alpha" });
    tick("beta");
    tick("pdf");
    fireEvent.click(within(bar()).getByRole("button", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete 2 skills?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 skills" }));
    await waitFor(() => expect(api.deleteUnmanagedSkill).toHaveBeenCalledTimes(2));
    expect(api.deleteUnmanagedSkill.mock.calls).toEqual([
      // The list's order: a duplicate before an unmanaged folder.
      ["u-cc", "pdf", "skills"],
      ["u-cc", "beta", "skills"],
    ]);
    expect(await screen.findByText("Deleted 2 skills")).toBeInTheDocument();
  });

  test("Adopt is disabled with a reason when no ticked row is unmanaged", async () => {
    stub();
    renderTab();
    await screen.findByRole("link", { name: "alpha" });
    tick("pdf");
    const adopt = within(bar()).getByRole("button", { name: "Adopt" });
    expect(adopt).toBeDisabled();
    expect(adopt).toHaveAttribute("title", "Only unmanaged folders can be adopted");
  });

  test("Esc and Clear empty the selection; the single-row buttons are unchanged", async () => {
    stub();
    renderTab();
    await screen.findByRole("link", { name: "alpha" });
    expect(screen.getAllByRole("button", { name: /^Adopt:/ })).toHaveLength(3);
    tick("alpha");
    expect(within(bar()).getByText("1 of 4 selected")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Selected skills" })).toBeNull();
    tick("alpha");
    fireEvent.click(within(bar()).getByRole("button", { name: "Clear" }));
    expect(screen.getByLabelText("Search skills")).toBeInTheDocument();
  });

  test("select-all reaches only what the search shows", async () => {
    stub();
    renderTab();
    await screen.findByRole("link", { name: "alpha" });
    // "ta" matches beta only.
    fireEvent.change(screen.getByLabelText("Search skills"), { target: { value: "ta" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Select all" }));
    expect(within(bar()).getByText("1 of 1 selected")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Select alpha" })).toBeNull();
  });
});
