// frontend/src/components/skills/SkillDetailPane.test.tsx
// The open skill in the Skills page's reading pane (spec skill-manager "Cover skill management on REST and the web", "Show the commands a skill
// declares it needs"): its four tabs at their own paths, the Files tab opening
// on SKILL.md, each agent's copy on Delivery, the declared commands on
// Requires (History has its own file), and the built-in skill's refusals. The
// page is mounted the way the router mounts it; only the api modules are
// mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { AgentOut } from "@/lib/api/agents";
import type { SkillFileNode, SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { BUILTIN_SKILL, makeAgent, makeSkill, renderSkillsPage, where } from "@/test/skillsPageKit";

const h = vi.hoisted(() => ({
  skills: [] as SkillOut[],
  agents: [] as AgentOut[],
  /** The generic agent resources, each with its own on/off switch. */
  agentResources: [] as { uid: string; enabled: boolean }[],
}));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(async () => ({ items: h.skills })),
    remove: vi.fn(async () => ({ kept_copies: [] })),
    filesTree: vi.fn(),
    fileContent: vi.fn(),
    writeFileContent: vi.fn(),
    verify: vi.fn(async () => ({ entries: [] })),
    repair: vi.fn(),
    compareCopy: vi.fn(),
    resolveCopy: vi.fn(),
    cancelStage: vi.fn(async () => undefined),
  },
}));
vi.mock("@/lib/api/agents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agents")>()),
  agentsApi: { list: vi.fn(async () => ({ items: h.agents })) },
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({
    GET: async () => ({
      data: {
        resources: h.agentResources.map((r) => ({ ...r, kind: "agent", scope: null })),
      },
      error: undefined,
    }),
  }),
}));

const { skillsApi } = await import("@/lib/api/skills");

const CC = makeAgent();
const CODEX = makeAgent({
  uid: "ag-cx",
  name: "codex",
  display_name: "Codex",
  type: "codex",
  config_dir: "/Users/me/.codex",
});

const TREE: SkillFileNode = {
  name: "hello",
  path: "",
  type: "dir",
  size: null,
  abs_path: "/Users/me/.coffer/skills/hello",
  folder_abs_path: "/Users/me/.coffer/skills/hello",
  truncated: false,
  children: [
    {
      name: "SKILL.md",
      path: "SKILL.md",
      type: "file",
      size: 40,
      abs_path: "/Users/me/.coffer/skills/hello/SKILL.md",
      folder_abs_path: "/Users/me/.coffer/skills/hello",
      truncated: false,
      children: [],
    },
    {
      name: "run.sh",
      path: "run.sh",
      type: "file",
      size: 10,
      abs_path: "/Users/me/.coffer/skills/hello/run.sh",
      folder_abs_path: "/Users/me/.coffer/skills/hello",
      truncated: false,
      children: [],
    },
  ],
};
const SKILL_MD = "# Say hello\n\nGreet the user by name.";

beforeEach(() => {
  h.skills = [makeSkill()];
  h.agents = [CC, CODEX];
  h.agentResources = [
    { uid: CC.uid, enabled: true },
    { uid: CODEX.uid, enabled: true },
  ];
  vi.mocked(skillsApi.filesTree).mockResolvedValue({ root: TREE });
  vi.mocked(skillsApi.verify).mockResolvedValue({ entries: [] });
  vi.mocked(skillsApi.fileContent).mockImplementation(async (_uid, path) => ({
    path,
    abs_path: `/Users/me/.coffer/skills/hello/${path}`,
    folder_abs_path: "/Users/me/.coffer/skills/hello",
    content: path === "SKILL.md" ? SKILL_MD : "echo hi",
    binary: false,
    truncated: false,
    size: 40,
    fingerprint: "fp-1",
  }));
});
afterEach(() => vi.clearAllMocks());

/** Radix tabs activate on mousedown, not click. */
function openTab(name: string) {
  fireEvent.mouseDown(screen.getByRole("tab", { name }));
}

acceptance("skill-manager", "a skill opens on its files with SKILL.md rendered", async () => {
  renderSkillsPage("/skills/hello");
  // The open skill's pane waits on the library and the skill's detail.
  const tabs = await screen.findAllByRole("tab", {}, { timeout: 5_000 });
  // No counts in the tab labels.
  expect(tabs.map((t) => t.textContent)).toEqual(["Files", "Delivery", "Requires", "History"]);
  expect(screen.getByRole("tab", { name: "Files" })).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByRole("tab", { name: "SKILL.md" })).not.toBeInTheDocument();
  // SKILL.md is open and rendered, not raw.
  expect(await screen.findByRole("heading", { name: "Say hello" })).toBeInTheDocument();
  expect(skillsApi.fileContent).toHaveBeenCalledWith("sk-11aa", "SKILL.md");

  // Source shows the raw text.
  fireEvent.click(screen.getByRole("button", { name: "Source" }));
  await waitFor(() =>
    expect(screen.queryByRole("heading", { name: "Say hello" })).not.toBeInTheDocument(),
  );
  expect(document.body.textContent).toContain("# Say hello");

  // Edit, then Save, writes through the conditional save.
  vi.mocked(skillsApi.writeFileContent).mockResolvedValue({
    path: "SKILL.md",
    abs_path: "/Users/me/.coffer/skills/hello/SKILL.md",
    folder_abs_path: "/Users/me/.coffer/skills/hello",
    content: "# Hi",
    binary: false,
    truncated: false,
    size: 4,
    fingerprint: "fp-2",
  });
  fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
  fireEvent.change(screen.getByRole("textbox", { name: /SKILL\.md/ }), {
    target: { value: "# Hi" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() =>
    expect(skillsApi.writeFileContent).toHaveBeenCalledWith("sk-11aa", {
      path: "SKILL.md",
      content: "# Hi",
      expected_fingerprint: "fp-1",
    }),
  );
});

test("the Files tab's tree and viewer sit in a split with a draggable divider", async () => {
  renderSkillsPage("/skills/hello");
  const divider = await screen.findByRole("separator", {}, { timeout: 5_000 });
  expect(divider).toHaveAttribute("aria-orientation", "vertical");
  expect(divider).toHaveAttribute("aria-valuenow");
  expect(screen.queryByRole("button", { name: /hide/i })).toBeNull();
});

acceptance("skill-manager", "the delivery tab shows each agent's copy", async () => {
  h.skills = [
    makeSkill({
      scope: { agents: [CC.uid] },
      bindings: [
        {
          agent_uid: CC.uid,
          agent_name: CC.name,
          last_linked_at: "2026-09-29T10:00:00Z",
          last_link_path: "/Users/me/.claude/skills/hello",
          link_mode: "symlink",
        },
      ],
    }),
  ];
  renderSkillsPage("/skills/hello/delivery");
  const first = await screen.findByTestId("skill-delivery-claude-code");
  expect(first).toHaveTextContent("Linked");
  expect(first).toHaveTextContent("~/.claude/skills/hello");
  const second = screen.getByTestId("skill-delivery-codex");
  expect(second).toHaveTextContent("Not delivered");
  expect(second).toHaveTextContent("Not ticked.");
  // Read-only: who gets the skill is the Reach button's, so no switches here.
  expect(screen.queryByRole("switch")).toBeNull();
  expect(screen.queryByRole("button", { name: /Deliver to all|Remove from all/ })).toBeNull();
});

acceptance("skill-manager", "a skill's requires tab links each command", async () => {
  h.skills = [
    makeSkill({
      requires: [
        { command: "jq", min_version: null },
        { command: "gh", min_version: "2.40" },
      ],
    }),
  ];
  renderSkillsPage("/skills/hello/requires");
  const [jq, gh] = await screen.findAllByRole("link", { name: "View in CLIs" });
  expect(jq).toHaveAttribute("href", "/clis/jq");
  expect(gh).toHaveAttribute("href", "/clis/gh");
  expect(screen.getByRole("tab", { name: "Requires" })).not.toHaveTextContent("·");
  fireEvent.click(gh);
  // The route for /clis/:command renders in the Skills page's place.
  expect(await screen.findByText("cli page")).toBeInTheDocument();
});

acceptance(
  "skill-manager",
  "the skills surface marks the built-in skill and offers no delete",
  async () => {
    h.skills = [BUILTIN_SKILL, makeSkill()];
    renderSkillsPage("/skills/coffer-guide");
    const header = (await screen.findByRole("heading", { name: "coffer-guide", level: 2 })).closest(
      "header",
    ) as HTMLElement;
    expect(within(header).getByTestId("skill-builtin-badge")).toHaveTextContent("Built-in");
    fireEvent.click(within(header).getByRole("button", { name: "More actions for coffer-guide" }));
    expect(await screen.findByRole("menuitem", { name: "Delete…" })).toBeDisabled();
    // No info banner for it: the Built-in badge says so.
    expect(screen.queryByTestId("skill-builtin-banner")).not.toBeInTheDocument();
    // Its row wears the mark too, and has no box: it is never part of a bulk action.
    const list = screen.getByTestId("skill-library");
    expect(within(list).getByTestId("skill-builtin-badge")).toBeInTheDocument();
    expect(within(list).queryByRole("checkbox", { name: /coffer-guide/ })).not.toBeInTheDocument();
    // Its files are read-only.
    expect(await screen.findByRole("heading", { name: "Say hello" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
  },
);

describe("SkillDetailPane", () => {
  test("each tab lives in the path, Files at the bare address", async () => {
    renderSkillsPage("/skills/hello");
    await screen.findAllByRole("tab");
    openTab("Delivery");
    await waitFor(() => expect(where.url).toBe("/skills/hello/delivery"));
    expect(screen.getByRole("tab", { name: "Delivery" })).toHaveAttribute("aria-selected", "true");
    openTab("Files");
    await waitFor(() => expect(where.url).toBe("/skills/hello"));
  });

  test("the open file is kept in ?file=", async () => {
    renderSkillsPage("/skills/hello?file=run.sh");
    await waitFor(() => expect(skillsApi.fileContent).toHaveBeenCalledWith("sk-11aa", "run.sh"));
    fireEvent.click(await screen.findByRole("treeitem", { name: "SKILL.md" }));
    await waitFor(() => expect(where.url).toBe("/skills/hello"));
  });

  test("the header shows name, state pill, source type, master path and when it changed — no description", async () => {
    renderSkillsPage("/skills/hello");
    expect(await screen.findByTestId("skill-master-path")).toHaveTextContent(
      "~/.coffer/skills/hello",
    );
    expect(screen.getByTestId("skill-detail-source")).toHaveTextContent("Folder");
    expect(screen.getByText(/^Updated /)).toBeInTheDocument();
    const header = screen
      .getByRole("heading", { name: "hello", level: 2 })
      .closest("header") as HTMLElement;
    expect(within(header).getByText("In use")).toBeInTheDocument();
    // The description is SKILL.md's, not the header's.
    expect(screen.queryByText("Say hello nicely.", { selector: "header *" })).toBeNull();
  });

  test("an off skill's pill says Off", async () => {
    h.skills = [makeSkill({ enabled: false })];
    renderSkillsPage("/skills/hello");
    const header = (await screen.findByRole("heading", { name: "hello", level: 2 })).closest(
      "header",
    ) as HTMLElement;
    // The pill and the Reach button both say Off.
    expect(within(header).getAllByText("Off")).toHaveLength(2);
  });

  test("Delete asks first, then removes the skill and returns to the library", async () => {
    renderSkillsPage("/skills/hello");
    const header = (await screen.findByRole("heading", { name: "hello", level: 2 })).closest(
      "header",
    ) as HTMLElement;
    fireEvent.click(within(header).getByRole("button", { name: "More actions for hello" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete hello?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete skill" }));
    await waitFor(() => expect(skillsApi.remove).toHaveBeenCalledWith("sk-11aa"));
    await waitFor(() => expect(where.url).toBe("/skills"));
  });

  test("delivery says why a copy is missing: the skill is off", async () => {
    h.skills = [makeSkill({ enabled: false })];
    renderSkillsPage("/skills/hello/delivery");
    await waitFor(() =>
      expect(screen.getByTestId("skill-delivery-codex")).toHaveTextContent("The skill is off."),
    );
  });

  test("delivery shows a copy that differs from master after Check again", async () => {
    h.skills = [
      makeSkill({
        bindings: [
          {
            agent_uid: CODEX.uid,
            agent_name: CODEX.name,
            last_linked_at: null,
            last_link_path: "/Users/me/.codex/skills/hello",
            link_mode: "symlink",
          },
        ],
      }),
    ];
    vi.mocked(skillsApi.verify).mockResolvedValue({
      entries: [
        {
          skill_name: "hello",
          agent_name: "codex",
          kind: "tampered_link",
          target_path: "/Users/me/.codex/skills/hello",
          handoff: null,
        },
      ],
    });
    renderSkillsPage("/skills/hello/delivery");
    const row = await screen.findByTestId("skill-delivery-codex");
    expect(row).toHaveTextContent("Linked");
    // Opening the page reads nothing: the copies are checked only on request.
    expect(skillsApi.verify).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(row).toHaveTextContent("Points elsewhere"));
    expect(row).toHaveTextContent("Coffer points it back on its next pass.");
  });

  test("a skill that declares no commands says so on Requires", async () => {
    renderSkillsPage("/skills/hello/requires");
    expect(await screen.findByText("Nothing required")).toBeInTheDocument();
  });

  test("an unknown name says there is no such skill", async () => {
    renderSkillsPage("/skills/nope");
    expect(await screen.findByText("This skill no longer exists")).toBeInTheDocument();
  });
});
