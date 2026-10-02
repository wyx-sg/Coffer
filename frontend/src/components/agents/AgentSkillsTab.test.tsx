// src/components/agents/AgentSkillsTab.test.tsx — the agent's Skills tab: Coffer's skills and the agent's own in one table.
//
// Covered: both owners listed with their state and owner, the owner filter kept
// in the URL, a name opening the right page, Adopt (and its failure staying on
// the row and under the table), Open file, Remove duplicate behind a confirm,
// and the shared empty state. The hooks run for real against mocked wire
// modules; the fixture agent's uid (`u-cc`) differs from its type so every
// assertion shows which one addresses what.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { AgentSkillsTab } from "./AgentSkillsTab";
import { pathText } from "@/test/truncatedPath";
import { ToastProvider } from "@/components/ui/toast";
import type { AgentOut } from "@/lib/api/agents";
import type { UnmanagedSkillOut } from "@/lib/api/agents-workspace";
import { ApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";

vi.mock("@/lib/api/agents", () => ({
  agentsApi: {
    unmanagedSkills: vi.fn(),
    adoptUnmanagedSkill: vi.fn(),
    deleteUnmanagedSkill: vi.fn(),
  },
}));
vi.mock("@/lib/api/skills", () => ({ skillsApi: { list: vi.fn() } }));
const openMock = vi.fn<(path: string, withApp: string) => Promise<void>>(() => Promise.resolve());
vi.mock("@/lib/fsActions", () => ({
  useFsActions: () => ({ open: openMock, reveal: vi.fn(() => Promise.resolve()) }),
}));

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

function skill(name: string, extra: Partial<SkillOut> = {}): SkillOut {
  return {
    uid: `s-${name}`,
    name,
    description: `${name} does things`,
    builtin: false,
    enabled: true,
    master_path: `/Users/me/.coffer/skills/${name}`,
    bindings: [
      {
        agent_uid: "u-cc",
        agent_name: "claude_code",
        last_link_path: `/Users/me/.claude/skills/${name}`,
        last_linked_at: null,
        link_mode: null,
      },
    ],
    ...extra,
  } as SkillOut;
}

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

const GUIDE = skill("coffer-guide", { builtin: true });
const OTHER_AGENT_SKILL = skill("codex-only", {
  bindings: [
    {
      agent_uid: "u-codex",
      agent_name: "codex",
      last_link_path: "/x",
      last_linked_at: null,
      link_mode: null,
    },
  ],
});
const LOOSE = own("release-notes");
const LINKED = own("lint-fix", {
  location: "agents_dir",
  path: "/Users/me/.agents/skills/lint-fix",
  foreign_link: true,
});
const BROKEN = own("migrate-old", { valid: false, reason: "SKILL.md has no name" });

function stub(skills: SkillOut[], unmanaged: UnmanagedSkillOut[]) {
  skillsList.mockResolvedValue({ items: skills } as Awaited<ReturnType<typeof skillsApi.list>>);
  api.unmanagedSkills.mockResolvedValue({ items: unmanaged });
  api.adoptUnmanagedSkill.mockResolvedValue({ uid: "s-new", name: "release-notes" });
  api.deleteUnmanagedSkill.mockResolvedValue(undefined);
}

function Where() {
  const loc = useLocation();
  return <p data-testid="where">{`${loc.pathname}${loc.search}`}</p>;
}

function renderTab() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/agents/claude_code/skills"]}>
          <Routes>
            <Route
              path="/agents/:type/skills"
              element={
                <>
                  <AgentSkillsTab agent={AGENT} />
                  <Where />
                </>
              }
            />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const row = (name: string) => screen.getByRole("link", { name }).closest("tr") as HTMLElement;

afterEach(() => vi.clearAllMocks());

describe("AgentSkillsTab", () => {
  test("lists Coffer's skills for this agent and the agent's own folders, each with its state", async () => {
    stub([GUIDE, OTHER_AGENT_SKILL], [LOOSE, LINKED, BROKEN]);
    renderTab();

    expect(
      await screen.findByText("4 skills · 1 delivered by Coffer · 3 the agent’s own"),
    ).toBeInTheDocument();
    expect(screen.queryByText("codex-only")).not.toBeInTheDocument();

    const guide = row("coffer-guide");
    expect(within(guide).getByText("Built in")).toBeInTheDocument();
    expect(within(guide).getByText(pathText("~/.claude/skills/coffer-guide"))).toBeInTheDocument();
    expect(within(guide).getByText("Linked")).toBeInTheDocument();
    expect(within(guide).getByText("Coffer’s")).toBeInTheDocument();

    expect(within(row("release-notes")).getByText("Not managed")).toBeInTheDocument();
    expect(within(row("release-notes")).getByText("The agent’s own")).toBeInTheDocument();
    expect(within(row("lint-fix")).getByText("Foreign link")).toBeInTheDocument();
    expect(within(row("migrate-old")).getByText("Invalid SKILL.md")).toBeInTheDocument();
    expect(within(row("migrate-old")).getByText("SKILL.md has no name")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skills" })).toHaveAttribute("href", "/skills");
  });

  acceptance("agent-registry", "the owner filter narrows an installed-kind tab", async () => {
    stub([GUIDE], [LOOSE, BROKEN]);
    renderTab();
    await screen.findByRole("link", { name: "coffer-guide" });

    fireEvent.click(screen.getByRole("radio", { name: "The agent’s own" }));
    expect(screen.queryByRole("link", { name: "coffer-guide" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "release-notes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "migrate-old" })).toBeInTheDocument();
    expect(screen.getAllByText("The agent’s own", { selector: "td span" })).toHaveLength(2);
    expect(screen.getByTestId("where")).toHaveTextContent("?owner=own");

    fireEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(screen.getByRole("link", { name: "coffer-guide" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(4);
  });

  acceptance(
    "skill-manager",
    "open an unmanaged skill's detail page from the agent's Skills tab",
    async () => {
      stub([GUIDE], [LINKED]);
      renderTab();
      fireEvent.click(await screen.findByRole("link", { name: "lint-fix" }));
      expect(screen.getByTestId("where")).toHaveTextContent(
        "/agents/claude_code/skills/unmanaged/agents_dir/lint-fix",
      );
    },
  );

  test("a Coffer skill's name opens its page on the Skills page", async () => {
    stub([GUIDE], []);
    renderTab();
    expect(await screen.findByRole("link", { name: "coffer-guide" })).toHaveAttribute(
      "href",
      "/skills/coffer-guide",
    );
  });

  // The Skills tab half of the scenario (Adopt adopts the folder by the
  // agent's uid; a foreign link cannot be adopted); the Skills page half is in
  // SkillsPage.test.tsx.
  acceptance(
    "skill-manager",
    "unmanaged skills are adopted only from the agent's Skills tab",
    async () => {
      stub([], [LOOSE, LINKED]);
      renderTab();
      expect(await screen.findByRole("button", { name: "Adopt: lint-fix" })).toBeDisabled();
      fireEvent.click(screen.getByRole("button", { name: "Adopt: release-notes" }));
      await waitFor(() =>
        expect(api.adoptUnmanagedSkill).toHaveBeenCalledWith("u-cc", "release-notes", "skills"),
      );
    },
  );

  test("a failed adoption stays on its row and under the table, with the way to the clashing skill", async () => {
    stub([skill("release-notes", { bindings: [] })], [own("release-notes")]);
    api.adoptUnmanagedSkill.mockRejectedValue(
      new ApiError("RESOURCE_ALREADY_EXISTS", "a skill with that name is already in the library"),
    );
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Adopt: release-notes" }));

    const alert = await screen.findByText(/Couldn’t adopt release-notes:/);
    expect(within(row("release-notes")).getByText("Adopt failed")).toBeInTheDocument();
    expect(
      within(alert.closest("[role=alert]") as HTMLElement).getByRole("link", { name: "Open it" }),
    ).toHaveAttribute("href", "/skills/release-notes");
  });

  test("a Coffer skill has no Open file button; an invalid folder's file opens from its menu", async () => {
    stub([GUIDE], [BROKEN]);
    renderTab();
    await screen.findByRole("button", { name: "More for migrate-old" });
    expect(screen.queryByRole("button", { name: "Open file: coffer-guide" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Open file: migrate-old" })).toBeNull();
    const more = screen.getByRole("button", { name: "More for migrate-old" });
    fireEvent.click(more);
    fireEvent.click(await screen.findByRole("menuitem", { name: "Open file" }));
    await waitFor(() => expect(openMock).toHaveBeenCalledTimes(1));
    expect(openMock).toHaveBeenCalledWith("/Users/me/.claude/skills/migrate-old/SKILL.md", "");
  });

  test("the ⋯ menu does not repeat the row's Adopt or Remove duplicate button", async () => {
    stub(
      [skill("pdf")],
      [
        own("pdf", { location: "agents_dir", path: "/Users/me/.agents/skills/pdf" }),
        own("release-notes"),
      ],
    );
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "More for pdf" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Open file"]);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    fireEvent.click(await screen.findByRole("button", { name: "More for release-notes" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).not.toContain("Adopt");
  });

  test("Remove duplicate deletes the agent's copy of a skill Coffer delivers, after a confirm", async () => {
    stub(
      [skill("pdf")],
      [own("pdf", { location: "agents_dir", path: "/Users/me/.agents/skills/pdf" })],
    );
    renderTab();
    expect(await screen.findByText("Duplicate of pdf in Coffer")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete duplicate: pdf" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/~\/\.agents\/skills\/pdf/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("u-cc", "pdf", "agents_dir"),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("an agent with no skills shows the shared empty state", async () => {
    stub([], []);
    renderTab();
    expect(await screen.findByText("Claude Code has no skills")).toBeInTheDocument();
  });
});
