// frontend/src/components/skills/SkillDetailPane.test.tsx
// The open skill in the Skills page's reading pane (spec skill-manager "Cover skill
// management on REST and on the Skills page", "Show the commands a skill declares it
// needs"): its three tabs at their own paths, the Files tab opening on SKILL.md
// read-only, each agent's copy on Delivery, the declared commands on Requires, its
// history in the ⋯ menu's History… dialog (no tab), and the built-in skill's
// refusals. The page is mounted the way the router mounts it; only the api modules
// are mocked.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";

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
    verify: vi.fn(async () => ({ entries: [] })),
    repair: vi.fn(),
    compareCopy: vi.fn(),
    resolveCopy: vi.fn(),
    cancelStage: vi.fn(async () => undefined),
  },
}));
vi.mock("@/lib/api/vault", () => ({ vaultApi: { historyHandoff: vi.fn() } }));
vi.mock("@/lib/api/agentProviders", () => ({
  agentProvidersApi: {
    list: vi.fn(async () => ({
      agents: [{ agent_key: "claude_code", display_name: "Claude Code", available: true }],
    })),
  },
}));
vi.mock("@/lib/api/fs", () => ({
  fsApi: {
    listTerminals: vi.fn(async () => []),
    openTerminal: vi.fn(async () => undefined),
    reveal: vi.fn(async () => undefined),
    open: vi.fn(async () => undefined),
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
const { vaultApi } = await import("@/lib/api/vault");
const { fsApi } = await import("@/lib/api/fs");

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
  expect(tabs.map((t) => t.textContent)).toEqual(["Files", "Delivery", "Requires"]);
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

  // The file is read-only: it opens in the person's editor, and nothing here edits it.
  expect(screen.getByRole("button", { name: "Open in editor" })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Reveal in Finder" })).toHaveLength(2);
  expect(screen.queryByRole("button", { name: /^edit$/i })).not.toBeInTheDocument();
});

test("the Files tab's tree and viewer sit in a split with a draggable divider", async () => {
  renderSkillsPage("/skills/hello");
  const divider = await screen.findByRole("separator", {}, { timeout: 5_000 });
  expect(divider).toHaveAttribute("aria-orientation", "vertical");
  expect(divider).toHaveAttribute("aria-valuenow");
  expect(screen.queryByRole("button", { name: /hide/i })).toBeNull();
});

acceptance("skill-manager", "a skill's history is handed to git and an agent", async () => {
  const VAULT = "/Users/me/.coffer/vault";
  vi.mocked(vaultApi.historyHandoff).mockImplementation(async (path) => ({
    path,
    vault_path: VAULT,
    absolute_path: `${VAULT}/${path}`,
    log_command: `git -C ${VAULT} log -p -- ${path}`,
    handoff: { prompt: `Restore ${path}.` },
  }));
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
  h.skills = [BUILTIN_SKILL, makeSkill()];
  renderSkillsPage("/skills/hello");
  const header = (await screen.findByRole("heading", { name: "hello", level: 2 })).closest(
    "header",
  ) as HTMLElement;
  // History is a ⋯ menu item, not a tab.
  expect(screen.queryByRole("tab", { name: "History" })).not.toBeInTheDocument();
  fireEvent.click(within(header).getByRole("button", { name: "More actions for hello" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "History…" }));

  const dialog = await screen.findByRole("dialog", { name: "History" });
  expect(within(dialog).getByTestId("vault-history-path")).toHaveTextContent("skills/hello/");
  await waitFor(() =>
    expect(within(dialog).getByRole("button", { name: "Copy git command" })).toBeEnabled(),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Copy git command" }));
  await waitFor(() =>
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      `git -C ${VAULT} log -p -- skills/hello/`,
    ),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Reveal in Finder" }));
  await waitFor(() => expect(fsApi.reveal).toHaveBeenCalledWith(`${VAULT}/skills/hello/`));
  // The restore is handed to the person's agent, with the prompt for this folder.
  fireEvent.click(within(dialog).getByRole("button", { name: /Hand off to Claude Code/ }));
  await waitFor(() =>
    expect(fsApi.openTerminal).toHaveBeenCalledWith(
      expect.objectContaining({ prompt: "Restore skills/hello/." }),
    ),
  );
  fireEvent.keyDown(dialog, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  // The built-in skill is regenerated from the build: its menu has no History….
  cleanup();
  renderSkillsPage("/skills/coffer-guide");
  const builtinHeader = (
    await screen.findByRole("heading", { name: "coffer-guide", level: 2 })
  ).closest("header") as HTMLElement;
  fireEvent.click(
    within(builtinHeader).getByRole("button", { name: "More actions for coffer-guide" }),
  );
  await screen.findByRole("menuitem", { name: "Delete…" });
  expect(screen.queryByRole("menuitem", { name: "History…" })).not.toBeInTheDocument();
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
