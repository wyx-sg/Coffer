// frontend/src/components/skills/SkillLibraryStates.test.tsx
// What the library and the open skill say before the reader asks (canvas
// 4.3.01, 4.3.07, 4.3.17, 4.3.20, 4.3.28): a row's second line names what
// needs attention — a command it needs is missing, a folder is in the way, an
// update is waiting — the open skill repeats it as a banner with its one
// action, and a folder in the skills store that no skill claims is listed
// under "Not in your library" and can be added or moved out.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { AgentOut } from "@/lib/api/agents";
import type { SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { JQ_MISSING } from "@/test/cliFixtures";
import { makeAgent, makeSkill, renderSkillsPage, where } from "@/test/skillsPageKit";
import { gitSkill } from "./skillSourceTestData";

const h = vi.hoisted(() => ({ skills: [] as SkillOut[], agents: [] as AgentOut[] }));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(async () => ({ items: h.skills })),
    filesTree: vi.fn(async () => ({ root: { name: "x", path: "", type: "dir", children: [] } })),
    fileContent: vi.fn(),
    verify: vi.fn(async () => ({ entries: [] })),
    repair: vi.fn(),
    checkSource: vi.fn(),
    orphans: vi.fn(async () => ({ items: [] })),
    adoptOrphan: vi.fn(),
    removeOrphan: vi.fn(async () => undefined),
    orphanFiles: vi.fn(),
    orphanFileContent: vi.fn(),
  },
}));
vi.mock("@/lib/api/clis", () => ({
  clisApi: { list: vi.fn(async () => ({ items: [JQ_MISSING], warnings: [] })), checkAll: vi.fn() },
}));
vi.mock("@/lib/api/agents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agents")>()),
  agentsApi: { list: vi.fn(async () => ({ items: h.agents })) },
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: async () => ({ data: { resources: [] }, error: undefined }) }),
}));

const { skillsApi } = await import("@/lib/api/skills");
const api = vi.mocked(skillsApi);

beforeEach(() => {
  h.agents = [makeAgent()];
  h.skills = [
    makeSkill({ requires: [{ command: "jq", min_version: null }] }),
    {
      ...gitSkill({
        update_available: true,
        latest_commit: "f9e8d7c6b5a4",
        commits_ahead: 3,
        files_changed: 2,
      }),
      name: "terraform-plan",
    },
  ];
});
afterEach(() => vi.clearAllMocks());

acceptance(
  "web-ui",
  "a library row says what needs attention in place of its description",
  async () => {
    renderSkillsPage("/skills");
    const list = await screen.findByTestId("skill-library");
    expect(await within(list).findByText("Needs jq · not installed")).toBeInTheDocument();
    expect(within(list).getByText("Update available · Git")).toBeInTheDocument();
  },
);

test("the open skill repeats a missing command as a banner", async () => {
  renderSkillsPage("/skills/hello");
  const banner = await screen.findByTestId("skill-banner-requires");
  expect(banner).toHaveTextContent("jq isn’t installed");
  expect(banner).toHaveTextContent("hello is still delivered");
});

acceptance(
  "web-ui",
  "a skill that needs a secret that is not set says so and links to Secrets",
  async () => {
    h.skills = [
      makeSkill({
        requires_secrets: [
          { name: "GITHUB_TOKEN", is_set: false },
          { name: "NPM_TOKEN", is_set: true },
        ],
      }),
    ];
    renderSkillsPage("/skills/hello");
    const list = await screen.findByTestId("skill-library");
    expect(
      await within(list).findByText("Needs secret GITHUB_TOKEN · not set"),
    ).toBeInTheDocument();
    const banner = await screen.findByTestId("skill-banner-secrets");
    expect(banner).toHaveTextContent("1 secret this skill needs is not set");
    expect(banner).toHaveTextContent("secret GITHUB_TOKEN is not set.");
    expect(banner).not.toHaveTextContent("NPM_TOKEN");
    const open = within(banner).getByRole("link", { name: "Open Secrets" });
    expect(open).toHaveAttribute("href", "/secrets");
  },
);

acceptance(
  "web-ui",
  "a skill whose tool is off says so in the list, the pill and a banner that opens the tool",
  async () => {
    h.skills = [
      makeSkill({
        requires_tools: [
          { name: "github", uid: "t-1", kind: "mcp_server", status: "off", why: null },
        ],
      }),
    ];
    renderSkillsPage("/skills/hello");
    const list = await screen.findByTestId("skill-library");
    expect(await within(list).findByText("Needs github · off")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "Needs attention" })).getAllByRole("link"),
    ).toHaveLength(1);
    const banner = await screen.findByTestId("skill-banner-tool");
    expect(banner).toHaveTextContent("github is off, so hello can’t call it");
    expect(within(banner).getByRole("link", { name: "Open github" })).toHaveAttribute(
      "href",
      "/mcp-servers/github",
    );
    // Turning a tool on is the person's choice: no hand-off in the banner.
    expect(within(banner).queryByRole("button", { name: /Copy prompt|Ask an agent/ })).toBeNull();
    const header = screen
      .getByRole("heading", { name: "hello", level: 2 })
      .closest("header") as HTMLElement;
    expect(within(header).getByText("Tool off")).toBeInTheDocument();
  },
);

test("a failing custom-tool group links to the group's page and says why", async () => {
  h.skills = [
    makeSkill({
      requires_tools: [
        {
          name: "billing-api",
          uid: "t-2",
          kind: "custom_tools",
          status: "failing",
          why: "401 from the API",
        },
      ],
    }),
  ];
  renderSkillsPage("/skills/hello");
  const banner = await screen.findByTestId("skill-banner-tool");
  expect(banner).toHaveTextContent("billing-api is failing");
  expect(banner).toHaveTextContent("401 from the API");
  expect(within(banner).getByRole("link", { name: "Open billing-api" })).toHaveAttribute(
    "href",
    "/custom-tools/billing-api",
  );
});

test("the commands banner carries one hand-off for every command that needs the person", async () => {
  renderSkillsPage("/skills/hello");
  const banner = await screen.findByTestId("skill-banner-requires");
  expect(
    within(banner).getAllByRole("button", { name: /Ask an agent|Copy prompt/ }).length,
  ).toBeGreaterThan(0);
});

test("a Git skill with an update offers Review update… above its tabs", async () => {
  renderSkillsPage("/skills/terraform-plan");
  const banner = await screen.findByTestId("skill-banner-update");
  expect(banner).toHaveTextContent("An update is available from github.com/acme/agent-skills");
  expect(banner).toHaveTextContent("main moved 3 commits past the pinned a1b2c3d");
  expect(within(banner).getByRole("button", { name: "Review update…" })).toBeInTheDocument();
  expect(screen.getByText("github.com/acme/agent-skills")).toBeInTheDocument();
});

test("an unreachable source says so and offers Check again", async () => {
  h.skills = [
    { ...gitSkill({ error: "repository not found.", checked_at: "2026-09-30T09:12:00Z" }) },
  ];
  api.checkSource.mockResolvedValue(h.skills[0].source_status!);
  renderSkillsPage("/skills/terraform-plan");
  const banner = await screen.findByTestId("skill-banner-unreachable");
  expect(banner).toHaveTextContent("Can’t reach github.com/acme/agent-skills");
  expect(banner).toHaveTextContent("only updates are paused");
  fireEvent.click(within(banner).getByRole("button", { name: "Check again" }));
  await waitFor(() => expect(api.checkSource).toHaveBeenCalledWith("sk-1"));
});

acceptance("web-ui", "a folder no skill claims is added in place or moved out", async () => {
  api.orphans.mockResolvedValue({
    items: [
      {
        name: "lint-rules",
        path: "/Users/me/.coffer/skills/lint-rules",
        valid: true,
        file_count: 3,
        description: "Team lint rules.",
        message: null,
        found_at: "2026-09-27T10:00:00Z",
      },
    ],
  });
  const file = (name: string) => ({
    name,
    path: name,
    abs_path: `/Users/me/.coffer/skills/lint-rules/${name}`,
    folder_abs_path: "/Users/me/.coffer/skills/lint-rules",
    type: "file" as const,
    size: 9,
    truncated: false,
    children: [],
  });
  api.orphanFiles.mockResolvedValue({
    root: { ...file(""), type: "dir", children: [file("SKILL.md"), file("rules.md")] },
  });
  api.orphanFileContent.mockResolvedValue({
    ...file("SKILL.md"),
    content: "# Lint rules",
    truncated: false,
    binary: false,
    size: 12,
    fingerprint: "fp",
  });
  api.adoptOrphan.mockResolvedValue(makeSkill({ uid: "sk-lr", name: "lint-rules" }));
  renderSkillsPage("/skills");
  const section = await screen.findByRole("list", { name: "Not in your library" });
  fireEvent.click(within(section).getByRole("link", { name: /lint-rules/ }));
  await waitFor(() => expect(where.url).toBe("/skills?orphan=lint-rules"));
  expect(await screen.findByText(/Valid SKILL\.md/)).toBeInTheDocument();
  // The meta line counts the files and says when it was found; the files show
  // in the read-only tree and reader.
  expect(screen.getByText("3 files")).toBeInTheDocument();
  expect(screen.getByText(/Found \d+ Sep/)).toBeInTheDocument();
  const tree = await screen.findByRole("navigation", { name: "Files" });
  expect(within(tree).getByRole("button", { name: /rules\.md/ })).toBeInTheDocument();
  await waitFor(() => expect(api.orphanFileContent).toHaveBeenCalledWith("lint-rules", "SKILL.md"));

  fireEvent.click(screen.getByRole("button", { name: "Delete folder…" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete the folder lint-rules?" });
  expect(dialog).toHaveTextContent("~/.coffer/content/backup/");
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(api.removeOrphan).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: "Add to library" }));
  await waitFor(() => expect(api.adoptOrphan).toHaveBeenCalledWith("lint-rules"));
  await waitFor(() => expect(where.url).toBe("/skills/lint-rules"));
});
