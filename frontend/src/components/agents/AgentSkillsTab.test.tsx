// src/components/agents/AgentSkillsTab.test.tsx — the agent's Skills tab: "From Coffer" in one row, then the agent's own skills.
//
// Covered: Coffer's skills as one row (count, first five names, a link to the
// Skills page filtered to this agent) and never as rows; the agent's own
// folders ordered worst first with their state, one button and a ⋯ menu that
// holds Delete… only; a name opening the folder's page; the Adopt dialog (name,
// conflict, reach, errors inside, closing on success); Delete duplicate behind a
// confirm; the shared empty box. The hooks run for real against mocked wire
// modules; the fixture agent's uid (`u-cc`) differs from its type so every
// assertion shows which one addresses what.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

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
  api.unmanagedSkillFiles.mockResolvedValue({
    root: {
      name: "release-notes",
      type: "dir",
      path: "",
      abs_path: "/x",
      folder_abs_path: "/x",
      size: null,
      truncated: false,
      children: [
        { name: "SKILL.md", type: "file", path: "SKILL.md", children: [] },
        { name: "notes.md", type: "file", path: "templates/notes.md", children: [] },
      ],
    },
  } as never);
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

const row = (name: string) => screen.getByRole("link", { name }).closest("li") as HTMLElement;

afterEach(() => vi.clearAllMocks());

describe("AgentSkillsTab", () => {
  acceptance(
    "agent-registry",
    "Coffer's part is one row and the agent's own items follow",
    async () => {
      // The owner filter is gone: Coffer's part is one row, the agent's own skills follow in a list.
      stub([GUIDE, OTHER_AGENT_SKILL], [LOOSE, BROKEN]);
      renderTab();
      expect(await screen.findByText("1 skill from Coffer")).toBeInTheDocument();
      expect(screen.queryByRole("radio")).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "coffer-guide" })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "release-notes" })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "migrate-old" })).toBeInTheDocument();
      expect(screen.getAllByRole("listitem")).toHaveLength(2);
    },
  );

  test("Coffer's skills are one row — count, first five names, a link filtered to this agent", async () => {
    const many = ["a", "b", "c", "d", "e", "f", "g"].map((n) => skill(`skill-${n}`));
    stub([...many, OTHER_AGENT_SKILL], []);
    renderTab();
    expect(await screen.findByText("7 skills from Coffer")).toBeInTheDocument();
    expect(
      screen.getByText("skill-a · skill-b · skill-c · skill-d · skill-e · +2 more"),
    ).toBeInTheDocument();
    expect(screen.queryByText("codex-only")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Skills/ })).toHaveAttribute(
      "href",
      "/skills?agent=u-cc",
    );
  });

  test("the agent's own skills are ordered invalid, foreign, duplicate, unmanaged, each with its state", async () => {
    stub(
      [skill("pdf")],
      [
        LOOSE,
        own("pdf", { location: "agents_dir", path: "/Users/me/.agents/skills/pdf" }),
        { ...LINKED, valid: false, reason: "symlink points outside the master store" },
        BROKEN,
      ],
    );
    renderTab();
    await screen.findByRole("link", { name: "migrate-old" });
    const names = screen.getAllByRole("link", {
      name: /^(release-notes|pdf|lint-fix|migrate-old)$/,
    });
    expect(names.map((n) => n.textContent)).toEqual([
      "migrate-old",
      "lint-fix",
      "pdf",
      "release-notes",
    ]);
    expect(within(row("migrate-old")).getByText("Invalid SKILL.md")).toBeInTheDocument();
    expect(within(row("migrate-old")).getByText("SKILL.md has no name")).toBeInTheDocument();
    expect(within(row("lint-fix")).getByText("Foreign link")).toBeInTheDocument();
    expect(within(row("pdf")).getByText("Duplicate")).toBeInTheDocument();
    expect(
      within(row("pdf")).getByText("Same name as Coffer’s pdf, which this agent already gets"),
    ).toBeInTheDocument();
    expect(within(row("release-notes")).getByText("Unmanaged")).toBeInTheDocument();
    expect(within(row("release-notes")).getByText("~/.claude/skills")).toBeInTheDocument();
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

  test("Adopt is hidden — not disabled — on an invalid folder and a foreign link", async () => {
    stub([], [LOOSE, LINKED, BROKEN]);
    renderTab();
    await screen.findByRole("link", { name: "lint-fix" });
    expect(screen.getAllByRole("button", { name: /^Adopt:/ })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Adopt: lint-fix" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Adopt: migrate-old" })).toBeNull();
  });

  // The Skills tab half of the scenario (the Adopt dialog adopts the folder by
  // the agent's uid, under the name and reach chosen); the Skills page half is
  // in SkillsPage.test.tsx.
  acceptance(
    "skill-manager",
    "unmanaged skills are adopted only from the agent's Skills tab",
    async () => {
      stub([], [LOOSE]);
      renderTab();
      fireEvent.click(await screen.findByRole("button", { name: "Adopt: release-notes" }));
      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByText("Adopt release-notes")).toBeInTheDocument();
      expect(within(dialog).getByLabelText("Name in Coffer")).toHaveValue("release-notes");
      expect(within(dialog).getByText("~/.claude/skills/release-notes")).toBeInTheDocument();
      expect(
        await within(dialog).findByText("2 files: SKILL.md, templates/notes.md"),
      ).toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole("button", { name: "Adopt" }));
      await waitFor(() =>
        expect(api.adoptUnmanagedSkill).toHaveBeenCalledWith("u-cc", "release-notes", "skills", {
          name: undefined,
          reach: { mode: "everywhere", agents: [] },
        }),
      );
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    },
  );

  acceptance("agent-registry", "adopting a skill asks for its name and reach", async () => {
    stub([], [LOOSE]);
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Adopt: release-notes" }));
    const dialog = await screen.findByRole("dialog");
    // The name is prefilled with the skill's own; the reach defaults to every agent.
    expect(within(dialog).getByLabelText("Name in Coffer")).toHaveValue("release-notes");
    expect(within(dialog).getByTestId("adopt-skill-reach")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Name in Coffer"), {
      target: { value: "notes" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt" }));
    await waitFor(() =>
      expect(api.adoptUnmanagedSkill).toHaveBeenCalledWith(
        "u-cc",
        "release-notes",
        "skills",
        expect.objectContaining({ name: "notes" }),
      ),
    );
  });

  test("a name Coffer already has is refused inline, with a way to the skill, before anything is sent", async () => {
    stub([skill("release-notes", { bindings: [] })], [LOOSE]);
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Adopt: release-notes" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText(
        "Coffer already has a skill named release-notes. Choose another name.",
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: "Open Coffer’s release-notes" }),
    ).toHaveAttribute("href", "/skills/release-notes");
    expect(within(dialog).getByRole("button", { name: "Adopt" })).toBeDisabled();
    expect(api.adoptUnmanagedSkill).not.toHaveBeenCalled();
  });

  test("a failed adoption stays in the dialog, which stays open and offers Retry", async () => {
    stub([], [LOOSE]);
    api.adoptUnmanagedSkill.mockRejectedValueOnce(
      new ApiError("INTERNAL_ERROR", "Permission denied writing to the library"),
    );
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Adopt: release-notes" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt" }));

    expect(await within(dialog).findByText("Couldn’t adopt release-notes")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(api.adoptUnmanagedSkill).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("the ⋯ menu holds Delete… only, and a duplicate has the Delete duplicate button instead", async () => {
    stub(
      [skill("pdf")],
      [
        own("pdf", { location: "agents_dir", path: "/Users/me/.agents/skills/pdf" }),
        own("release-notes"),
      ],
    );
    renderTab();
    await screen.findByRole("link", { name: "pdf" });
    expect(screen.queryByRole("button", { name: "More for pdf" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "More for release-notes" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Delete…"]);
  });

  test("Delete… names the folder and its files, and deletes it after the confirm", async () => {
    stub([], [LOOSE]);
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "More for release-notes" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText(
        "This deletes ~/.claude/skills/release-notes and its 2 files. Coffer has no copy, so it can’t be restored.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("u-cc", "release-notes", "skills"),
    );
  });

  test("Delete duplicate deletes the agent's copy of a skill Coffer delivers, after a confirm", async () => {
    stub(
      [skill("pdf")],
      [own("pdf", { location: "agents_dir", path: "/Users/me/.agents/skills/pdf" })],
    );
    renderTab();
    fireEvent.click(await screen.findByRole("button", { name: "Delete duplicate: pdf" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/~\/\.agents\/skills\/pdf/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.deleteUnmanagedSkill).toHaveBeenCalledWith("u-cc", "pdf", "agents_dir"),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("search narrows the agent's own list", async () => {
    stub([], [LOOSE, BROKEN]);
    renderTab();
    await screen.findByRole("link", { name: "release-notes" });
    fireEvent.change(screen.getByLabelText("Search skills"), { target: { value: "migrate" } });
    expect(screen.queryByRole("link", { name: "release-notes" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "migrate-old" })).toBeInTheDocument();
  });

  test("an agent with no skills of its own shows the shared empty box, search kept", async () => {
    stub([GUIDE], []);
    renderTab();
    expect(await screen.findByText("Claude Code has no skills of its own")).toBeInTheDocument();
    expect(screen.getByLabelText("Search skills")).toBeInTheDocument();
  });
});
