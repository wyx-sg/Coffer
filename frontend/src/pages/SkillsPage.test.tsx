// frontend/src/pages/SkillsPage.test.tsx
// The Skills page as a library beside a reading pane (spec skill-manager
// "Cover skill management on REST, the CLI and the web", "Report skill drift
// on request"): what the library lists and marks, the first-run state, the
// selection bar, Check copies, and the old addresses that must keep working.
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
    remove: vi.fn(async () => undefined),
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
vi.mock("@/lib/api/client", () => ({ getApiClient: () => h.client }));

const { skillsApi } = await import("@/lib/api/skills");

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
  const list = await screen.findByRole("list", { name: "Library" });
  return within(list).queryAllByRole("link");
}

acceptance("skill-manager", "desktop and CLI cover every operation", async () => {
  renderSkillsPage("/skills");
  expect(screen.getByRole("heading", { name: /^skills$/i })).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /hello/ })).toBeInTheDocument();
  // Search, the On / Off filter and Check copies sit over the library.
  expect(screen.getByRole("textbox", { name: "Filter skills" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Show" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Check copies" })).toBeInTheDocument();

  // One Add skill action, opening the add dialog.
  fireEvent.click(screen.getByRole("button", { name: /add skill/i }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
});

acceptance("skill-manager", "the skills page lists only managed skills", async () => {
  renderSkillsPage("/skills");
  const rows = await libraryRows();
  // The daemon's list is the managed skills; the page adds nothing to it and
  // offers no way to adopt an agent's own folder.
  expect(rows).toHaveLength(1);
  expect(rows[0]).toHaveTextContent("hello");
  expect(screen.queryByRole("button", { name: /adopt/i })).not.toBeInTheDocument();
  expect(skillsApi.list).toHaveBeenCalledTimes(1);
});

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

acceptance("skill-manager", "the old overview address opens delivery", async () => {
  h.skills = [makeSkill({ uid: "sk-0rel", name: "release-notes" })];
  renderSkillsPage("/skills/sk-0rel?tab=overview");
  await waitFor(() => expect(where.url).toBe("/skills/release-notes/delivery"));
  expect(await screen.findByRole("tab", { name: "Delivery", selected: true })).toBeInTheDocument();
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
    renderSkillsPage("/skills");
    const [row] = await libraryRows();
    expect(within(row).getByTestId("skill-degraded-badge")).toHaveTextContent("Copied");
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
    suggested_remedy: "Re-create the link.",
  };
  const foreign: SkillDriftEntry = {
    skill_name: "frontend-design",
    agent_name: "codex",
    kind: "replaced_with_regular",
    target_path: "/Users/me/.codex/skills/frontend-design",
    suggested_remedy: "Move the folder aside, then repair.",
  };
  vi.mocked(skillsApi.verify).mockResolvedValue({ entries: [missing, foreign] });
  vi.mocked(skillsApi.repair).mockResolvedValue({
    remediated: [missing],
    remaining: { entries: [foreign] },
  });
  renderSkillsPage("/skills");
  await libraryRows();

  fireEvent.click(screen.getByRole("button", { name: "Check copies" }));
  const panel = await screen.findByRole("region", { name: "Check agents’ copies" });
  const findings = await within(panel).findAllByTestId("skill-copy-finding");
  expect(findings).toHaveLength(2);
  expect(findings[0]).toHaveTextContent("deep-research");
  expect(findings[0]).toHaveTextContent("Codex");
  expect(findings[0]).toHaveTextContent("~/.codex/skills/deep-research");
  expect(findings[0]).toHaveTextContent("Link missing");
  expect(findings[1]).toHaveTextContent("Folder in the way");
  // Checking is read-only: nothing has been repaired yet.
  expect(skillsApi.repair).not.toHaveBeenCalled();

  fireEvent.click(within(panel).getByRole("button", { name: "Repair" }));
  await waitFor(() => expect(skillsApi.repair).toHaveBeenCalledTimes(1));
  // The missing link is put back; the foreign folder is left and stays listed.
  await waitFor(() => expect(within(panel).getByText("Repaired by Coffer")).toBeInTheDocument());
  const after = within(panel).getAllByTestId("skill-copy-finding");
  const stays = after.find((f) => f.textContent?.includes("frontend-design"));
  expect(stays).toHaveTextContent("Needs you");
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
    expect(await screen.findByText("Choose a skill")).toBeInTheDocument();
  });

  test("the On / Off filter and the search narrow the library", async () => {
    h.skills = [
      makeSkill({ uid: "a", name: "alpha" }),
      makeSkill({ uid: "b", name: "beta", enabled: false, description: "second" }),
    ];
    renderSkillsPage("/skills");
    expect(await libraryRows()).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Off" }));
    let rows = await libraryRows();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("beta");
    // An off skill says so where its reach would be.
    expect(rows[0]).toHaveTextContent("Off");

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Filter skills" }), {
      target: { value: "alp" },
    });
    rows = await libraryRows();
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
      dismissed_commit: null,
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
    expect(rows.find((r) => r.textContent?.includes("upd"))).toHaveTextContent("Update available");
    expect(rows.find((r) => r.textContent?.includes("err"))).toHaveTextContent(
      "Source unreachable",
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
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(skillsApi.remove).toHaveBeenCalledWith("sk-11aa"));
  });

  test("a failed list shows the error with a retry", async () => {
    vi.mocked(skillsApi.list).mockRejectedValueOnce(new Error("boom"));
    renderSkillsPage("/skills");
    expect(await screen.findByText("Failed to load skills")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
