// frontend/src/pages/SkillsPage.test.tsx
// The Skills page as a library beside a reading pane (spec skill-manager
// "Manage skills on REST and on the Skills page", "Report skill drift
// on request"): what the library lists and marks, the first-run state, the
// selection bar and Check copies.
// Only the network boundary is mocked — the skills, agents and generic
// resource api modules.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { AgentOut } from "@/lib/api/agents";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { BUILTIN_SKILL, makeAgent, makeSkill, renderSkillsPage, where } from "@/test/skillsPageKit";

const h = vi.hoisted(() => ({
  skills: [] as SkillOut[],
  agents: [] as AgentOut[],
  client: {
    GET: async () => ({ data: { resources: [] }, error: undefined }),
    POST: async () => ({ data: undefined, error: undefined }),
    PUT: async () => ({ data: undefined, error: undefined }),
    PATCH: async () => ({ data: undefined, error: undefined }),
    DELETE: async () => ({ data: undefined, error: undefined }),
  },
}));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(async () => ({ items: h.skills })),
    remove: vi.fn(async () => ({ kept_copies: [] })),
    bulkDelete: vi.fn(async (uids: string[]) => ({
      results: uids.map((uid) => ({
        uid,
        name: uid,
        deleted: true,
        kept_copies: [],
        error_code: null,
        error_message: null,
        error_details: null,
      })),
    })),
    filesTree: vi.fn(async () => ({ root: null })),
    fileContent: vi.fn(),
    writeFileContent: vi.fn(),
    verify: vi.fn(),
    repair: vi.fn(),
    stageFolder: vi.fn(),
    stageArchive: vi.fn(),
    stageGit: vi.fn(),
    confirmStage: vi.fn(),
    cancelStage: vi.fn(async () => undefined),
  },
}));
vi.mock("@/lib/api/agents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agents")>()),
  agentsApi: { list: vi.fn(async () => ({ items: h.agents })) },
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => h.client,
}));

const { skillsApi } = await import("@/lib/api/skills");
// The reading pane is a lazy chunk. Its first import transforms the pane's whole
// module graph, which on a loaded CI runner takes longer than a findBy* waits —
// so the test that opens it first failed there, not on a fast machine. Load it
// once, before any test, so every test sees a warm module.
await import("@/components/skills/SkillDetailPane");

const CC = makeAgent();
const CODEX = makeAgent({
  uid: "ag-cx",
  name: "codex",
  display_name: "Codex",
  type: "codex",
  config_dir: "/Users/me/.codex",
});

beforeEach(() => {
  h.skills = [makeSkill()];
  h.agents = [CC, CODEX];
});
afterEach(() => vi.clearAllMocks());

/** The library's rows, by the link each one is. */
async function libraryRows() {
  const list = await screen.findByTestId("skill-library");
  return within(list).queryAllByRole("link");
}

acceptance(
  "web-ui",
  "the library filters by reach and groups skills by what they need",
  async () => {
    h.skills = [
      makeSkill({ uid: "sk-1", name: "everywhere-skill" }),
      makeSkill({ uid: "sk-2", name: "off-skill", enabled: false }),
      makeSkill({ uid: "sk-3", name: "scoped-skill", scope: { agents: [CC.uid] } }),
    ];
    renderSkillsPage("/skills");
    expect(await libraryRows()).toHaveLength(3);
    const off = within(screen.getByRole("region", { name: "Off" }));
    expect(off.getByRole("link", { name: /off-skill/ })).toBeInTheDocument();
    const inUse = within(screen.getByRole("region", { name: "In use" }));
    expect(inUse.getAllByRole("link")).toHaveLength(2);

    // Radix Select opens from the keyboard in jsdom (no PointerEvent).
    const reach = screen.getByRole("combobox", { name: "Reach" });
    fireEvent.keyDown(reach, { key: "ArrowDown" });
    fireEvent.click(await screen.findByRole("option", { name: "Codex" }));
    await waitFor(() => expect(where.url).toBe(`/skills?agent=${CODEX.uid}`));
    const rows = await libraryRows();
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining("everywhere-skill")]);
  },
);

acceptance("skill-manager", "the web UI and REST cover every operation", async () => {
  renderSkillsPage("/skills");
  expect(screen.getByRole("heading", { name: /^skills$/i })).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /hello/ })).toBeInTheDocument();
  // Search and Check copies sit side by side over the library.
  expect(screen.getByRole("textbox", { name: "Filter skills" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Check copies" })).toBeInTheDocument();

  // One Add skill action, opening the add dialog.
  fireEvent.click(screen.getAllByRole("button", { name: /add skill/i })[0]);
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
});

// The Skills page half of "unmanaged skills are adopted only from the agent's
// Skills tab"; the Skills tab half is in AgentSkillsTab.test.tsx.
const listsOnlyManaged = async () => {
  renderSkillsPage("/skills");
  const rows = await libraryRows();
  // The daemon's list is the managed skills; the page adds nothing to it and
  // offers no way to adopt an agent's own folder.
  expect(rows).toHaveLength(1);
  expect(rows[0]).toHaveTextContent("hello");
  expect(screen.queryByRole("button", { name: /adopt/i })).not.toBeInTheDocument();
  expect(skillsApi.list).toHaveBeenCalledTimes(1);
};
acceptance("skill-manager", "the skills page lists only managed skills", listsOnlyManaged);
acceptance(
  "skill-manager",
  "unmanaged skills are adopted only from the agent's Skills tab",
  listsOnlyManaged,
);

acceptance("skill-manager", "the skills page lists only managed skills", async () => {
  // With no managed skill at all, the empty state points at the agents' own
  // Skills tabs and lists nothing from them.
  h.skills = [];
  renderSkillsPage("/skills");
  expect(await screen.findByText("No skills yet")).toBeInTheDocument();
  expect(await libraryRows()).toHaveLength(0);
  expect(screen.getByText(/own skills are on each agent’s Skills tab/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open Agents" })).toHaveAttribute("href", "/agents");
});

acceptance(
  "skill-manager",
  "fall back to a copy where a directory link cannot be made",
  async () => {
    h.skills = [
      makeSkill({
        bindings: [
          {
            agent_uid: CC.uid,
            agent_name: CC.name,
            last_linked_at: null,
            last_link_path: "/Users/me/.claude/skills/hello",
            link_mode: "copy_fallback",
          },
        ],
      }),
    ];
    // The Delivery tab says so, as a working delivery: no warning mark in the list.
    renderSkillsPage("/skills/hello/delivery");
    const row = await screen.findByTestId("skill-delivery-claude-code");
    expect(row).toHaveTextContent("Copied, not linked");
    expect(row).toHaveTextContent("Links aren’t allowed in ~/.claude/skills on this Mac");
    expect(screen.queryByTestId("skill-degraded-badge")).not.toBeInTheDocument();
  },
);

acceptance("skill-manager", "check agents' copies from the skills page", async () => {
  h.skills = [
    makeSkill({ name: "deep-research" }),
    makeSkill({ uid: "sk-fd", name: "frontend-design" }),
  ];
  const missing: SkillDriftEntry = {
    skill_name: "deep-research",
    agent_name: "codex",
    kind: "missing_link",
    target_path: "/Users/me/.codex/skills/deep-research",
    handoff: null,
  };
  const foreign: SkillDriftEntry = {
    skill_name: "frontend-design",
    agent_name: "codex",
    kind: "replaced_with_regular",
    target_path: "/Users/me/.codex/skills/frontend-design",
    handoff: { prompt: "Compare it with Coffer's copy." },
  };
  vi.mocked(skillsApi.verify).mockResolvedValue({ entries: [missing, foreign] });
  vi.mocked(skillsApi.repair).mockResolvedValue({
    remediated: [missing],
    remaining: { entries: [foreign] },
  });
  renderSkillsPage("/skills");
  await libraryRows();

  fireEvent.click(screen.getByRole("button", { name: "Check copies" }));
  const panel = await screen.findByRole("region", { name: "Check copies" });
  const findings = await within(panel).findAllByTestId("skill-copy-finding");
  expect(findings).toHaveLength(2);
  expect(findings[0]).toHaveTextContent("deep-research");
  expect(findings[0]).toHaveTextContent("Codex");
  expect(findings[0]).toHaveTextContent("Link missing");
  expect(findings[0]).toHaveTextContent("~/.codex/skills/deep-research");
  expect(findings[1]).toHaveTextContent("Folder in the way");
  // Repair is the fix for the missing link; the folder in the way is a choice
  // the person makes in the compare dialog, so no hand-off sits beside it.
  expect(findings[0]).toHaveTextContent("Repair puts it back");
  expect(within(findings[1]).queryByRole("button", { name: "Copy prompt" })).toBeNull();
  // Checking is read-only: nothing has been repaired yet.
  expect(skillsApi.repair).not.toHaveBeenCalled();

  fireEvent.click(within(panel).getByRole("button", { name: "Repair" }));
  await waitFor(() => expect(skillsApi.repair).toHaveBeenCalledTimes(1));
  // The missing link is put back and moves to Fixed by Coffer; the foreign
  // folder is left and stays under Needs you.
  await waitFor(() => expect(within(panel).getByText("Fixed by Coffer")).toBeInTheDocument());
  expect(within(panel).getByText("Link put back")).toBeInTheDocument();
  const stays = within(panel)
    .getAllByTestId("skill-copy-finding")
    .find((f) => f.textContent?.includes("frontend-design"));
  expect(within(stays as HTMLElement).getByRole("button", { name: "Review…" })).toBeInTheDocument();
});

describe("SkillsPage library", () => {
  test("with only the built-in guide it shows the first run, with one button per source", async () => {
    h.skills = [BUILTIN_SKILL];
    renderSkillsPage("/skills");
    expect(await screen.findByText("Only Coffer’s own guide so far")).toBeInTheDocument();
    for (const label of ["Add from folder", "Add from archive", "Add from Git"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole("button", { name: "Add from Git" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  test("nothing selected asks the reader to choose a skill", async () => {
    renderSkillsPage("/skills");
    expect(await screen.findByText("Nothing selected")).toBeInTheDocument();
  });

  test("the list column is folded by dragging its divider, not by a button", async () => {
    renderSkillsPage("/skills");
    await screen.findByText("Nothing selected");
    expect(screen.getByRole("separator")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /hide list/i })).toBeNull();
  });

  test("the search narrows the library; an off skill sits in Off without a reach word", async () => {
    h.skills = [
      makeSkill({ uid: "a", name: "alpha" }),
      makeSkill({ uid: "b", name: "beta", enabled: false, description: "second" }),
    ];
    renderSkillsPage("/skills");
    expect(await libraryRows()).toHaveLength(2);
    const off = within(screen.getByRole("region", { name: "Off" }));
    expect(off.getByRole("link", { name: /beta/ })).not.toHaveTextContent("second");

    fireEvent.change(screen.getByRole("textbox", { name: "Filter skills" }), {
      target: { value: "alp" },
    });
    const rows = await libraryRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("alpha");
  });

  test("a Git skill's row says when an update waits or its source is unreachable", async () => {
    const git = {
      type: "git_import" as const,
      url: "https://example.com/r.git",
      ref: null,
      subpath: "",
      commit: "abc",
      content_hash: "h",
    };
    const status = {
      checked_at: null,
      commits_ahead: 0,
      commits: [],
      compare_url: null,
      error: null,
      files_changed: 0,
      last_success_at: null,
      latest_commit: null,
      update_available: false,
    };
    h.skills = [
      makeSkill({
        uid: "u",
        name: "upd",
        source: git,
        source_status: { ...status, update_available: true },
      }),
      makeSkill({
        uid: "e",
        name: "err",
        source: git,
        source_status: { ...status, error: "no route" },
      }),
    ];
    renderSkillsPage("/skills");
    const rows = await libraryRows();
    expect(rows.find((r) => r.textContent?.includes("upd"))).toHaveTextContent(
      "Update available · Git",
    );
    expect(rows.find((r) => r.textContent?.includes("err"))).toHaveTextContent(
      "Git source unreachable",
    );
  });

  test("ticking rows shows the bulk bar with reach and Delete; the built-in row has no box", async () => {
    h.skills = [BUILTIN_SKILL, makeSkill()];
    renderSkillsPage("/skills");
    await libraryRows();
    expect(screen.queryByRole("checkbox", { name: /coffer-guide/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: /hello/ }));
    const bar = screen.getByRole("region", { name: "Selected skills" });
    expect(bar).toHaveTextContent("1 selected");
    expect(within(bar).getByTestId("bulk-reach-control")).toBeInTheDocument();
    fireEvent.click(within(bar).getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete 1 skill?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 1 skill" }));
    await waitFor(() => expect(skillsApi.bulkDelete).toHaveBeenCalledWith(["sk-11aa"]));
  });

  acceptance(
    "web-ui",
    "selected skills are set or deleted together from the bar above the list",
    async () => {
      h.skills = [BUILTIN_SKILL, makeSkill(), makeSkill({ uid: "sk-pdf", name: "pdf" })];
      renderSkillsPage("/skills");
      await libraryRows();
      fireEvent.click(screen.getByRole("checkbox", { name: /hello/ }));
      fireEvent.click(screen.getByRole("checkbox", { name: /pdf/ }));
      expect(await screen.findByText("2 skills selected")).toBeInTheDocument();
      expect(
        screen.getByText(/hello and pdf\. Set who gets them or delete them from the bar/),
      ).toBeInTheDocument();
      expect(
        screen.getByText("coffer-guide can’t be selected", { exact: false }),
      ).toBeInTheDocument();
      // The pane repeats nothing the bar has; it offers Check copies of the selection.
      expect(screen.getAllByRole("button", { name: /^Delete/ })).toHaveLength(1);
      expect(screen.getByRole("button", { name: "Check copies of 2 skills" })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Delete" }));
      const dialog = await screen.findByRole("dialog", { name: "Delete 2 skills?" });
      fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 skills" }));
      await waitFor(() => expect(skillsApi.bulkDelete).toHaveBeenCalledWith(["sk-11aa", "sk-pdf"]));
    },
  );

  test("a failed list shows the error with a retry", async () => {
    vi.mocked(skillsApi.list).mockRejectedValueOnce(new Error("boom"));
    renderSkillsPage("/skills");
    expect(await screen.findByText("Couldn’t load skills")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
