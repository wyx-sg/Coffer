// frontend/src/components/skills/SkillDetailRepair.test.tsx
// The open skill when something needs the reader (canvas 4.3.06, 4.3.23,
// 4.3.27, 4.3.41): a folder in the way of an agent's link is compared and
// resolved with one of two confirmed choices, a delete Coffer refuses stays in
// its dialog and says why, the "⋯" menu carries the page note's actions, and a
// skill whose master folder is gone offers the ways forward. Mounted the way
// the router mounts the page; only the api modules are mocked.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import type { AgentOut } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { acceptance } from "@/test/acceptance";
import { makeAgent, makeSkill, renderSkillsPage } from "@/test/skillsPageKit";

const h = vi.hoisted(() => ({ skills: [] as SkillOut[], agents: [] as AgentOut[] }));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(async () => ({ items: h.skills })),
    remove: vi.fn(),
    filesTree: vi.fn(async () => ({
      root: { name: "hello", path: "", type: "dir", children: [] },
    })),
    fileContent: vi.fn(),
    verify: vi.fn(),
    repair: vi.fn(),
    compareCopy: vi.fn(),
    resolveCopy: vi.fn(),
    orphans: vi.fn(async () => ({ items: [] })),
  },
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

const CC = makeAgent();
const CODEX = makeAgent({ uid: "ag-cx", name: "codex", display_name: "Codex", type: "codex" });
const LINK = "/Users/me/.codex/skills/hello";
const IN_THE_WAY = {
  skill_name: "hello",
  agent_name: "codex",
  kind: "replaced_with_regular" as const,
  target_path: LINK,
  handoff: null,
};

beforeEach(() => {
  h.agents = [CC, CODEX];
  h.skills = [
    makeSkill({
      bindings: [
        {
          agent_uid: CC.uid,
          agent_name: CC.name,
          last_linked_at: null,
          last_link_path: "/Users/me/.claude/skills/hello",
          link_mode: "symlink",
        },
        {
          agent_uid: CODEX.uid,
          agent_name: CODEX.name,
          last_linked_at: null,
          last_link_path: LINK,
          link_mode: "symlink",
        },
      ],
    }),
  ];
  api.verify.mockResolvedValue({ entries: [] });
});
afterEach(() => vi.clearAllMocks());

acceptance(
  "web-ui",
  "a folder in the way of a skill's link is resolved by a confirmed choice",
  async () => {
    api.verify.mockResolvedValue({ entries: [IN_THE_WAY] });
    api.compareCopy.mockResolvedValue({
      skill_uid: "sk-11aa",
      agent_uid: CODEX.uid,
      agent_name: "codex",
      path: LINK,
      kind: "replaced_with_regular",
      modified_at: null,
      changes: [
        {
          path: "SKILL.md",
          status: "modified",
          diff: "@@ -1,1 +1,1 @@\n-master text\n+agent text\n",
          binary: false,
          additions: 1,
          deletions: 1,
          truncated: false,
        },
      ],
    });
    api.resolveCopy.mockResolvedValue(h.skills[0]);
    renderSkillsPage("/skills/hello/delivery");

    // Nothing is read on opening; the person asks with Check again.
    fireEvent.click(await screen.findByRole("button", { name: "Check again" }));
    const banner = await screen.findByTestId("skill-banner-folder");
    expect(banner).toHaveTextContent("Coffer left Codex's folder alone — it needs you");
    expect(api.verify).toHaveBeenCalledTimes(1);
    fireEvent.click(within(banner).getByRole("button", { name: "Review…" }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("a folder is in the way in Codex");
    await waitFor(() => expect(api.compareCopy).toHaveBeenCalledWith("sk-11aa", CODEX.uid));
    // Keeping master shows what happens to the agent's folder.
    expect(await within(dialog).findByText("master text")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("radio", { name: /Replace it with Coffer’s link/ }),
    ).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(dialog).getByRole("radio", { name: /Adopt this folder/ }));
    expect(within(dialog).getByText(/so Claude Code gets them too/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Adopt this folder" }));
    await waitFor(() =>
      expect(api.resolveCopy).toHaveBeenCalledWith("sk-11aa", CODEX.uid, "agent"),
    );
  },
);

acceptance(
  "web-ui",
  "a delete refused because a copy is not Coffer's stays open and offers to keep that folder",
  async () => {
    api.remove.mockRejectedValueOnce(
      new ApiError("SKILL_COPY_NOT_OURS", "not ours", { path: LINK, agent_name: "codex" }),
    );
    api.remove.mockResolvedValueOnce({ kept_copies: [{ agent_name: "codex", path: LINK }] });
    renderSkillsPage("/skills/hello");
    fireEvent.click(await screen.findByRole("button", { name: "More actions for hello" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete hello?" });
    expect(dialog).toHaveTextContent("from the 2 agents that have it: Claude Code and Codex");
    expect(dialog).toHaveTextContent("The vault’s git history keeps the files");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete skill" }));
    // The error stays in the dialog; nothing else changed.
    expect(await within(dialog).findByText("Nothing was deleted")).toBeInTheDocument();
    expect(dialog).toHaveTextContent("is a regular folder now, not Coffer’s link");
    expect(dialog).toHaveTextContent("Coffer only removes what it made");
    expect(within(dialog).queryByRole("button", { name: "Retry" })).toBeNull();
    // The primary button now deletes the skill and leaves that folder to the agent.
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete, keep Codex’s folder" }));
    await waitFor(() => expect(api.remove).toHaveBeenLastCalledWith("sk-11aa", true));
  },
);

test("a delete that fails for another reason is the usual error with Retry", async () => {
  api.remove.mockRejectedValue(new ApiError("INTERNAL_ERROR", "boom"));
  renderSkillsPage("/skills/hello");
  fireEvent.click(await screen.findByRole("button", { name: "More actions for hello" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Delete…" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete hello?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete skill" }));
  expect(await within(dialog).findByText("Couldn’t delete hello")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("the skill menu carries the page note's actions, not the reach button's or the Delivery tab's", async () => {
  renderSkillsPage("/skills/hello");
  fireEvent.click(await screen.findByRole("button", { name: "More actions for hello" }));
  const items = await screen.findAllByRole("menuitem");
  expect(items.map((i) => i.textContent)).toEqual([
    "Open in editor",
    "Reveal in Finder",
    "Copy master path",
    "History…",
    "Delete…",
  ]);
});

acceptance("web-ui", "a skill whose master folder is gone offers the ways forward", async () => {
  h.skills = [makeSkill({ enabled: false, master_missing: true, bindings: [] })];
  renderSkillsPage("/skills/hello");
  const banner = await screen.findByTestId("skill-banner-master");
  expect(banner).toHaveTextContent("The master folder is gone");
  const header = screen
    .getByRole("heading", { name: "hello", level: 2 })
    .closest("header") as HTMLElement;
  expect(within(header).getByText("Master missing")).toBeInTheDocument();
  // Both ways forward are in the banner: the hand-off that looks for a copy, and Delete skill….
  expect(within(banner).getByRole("button", { name: "Copy prompt" })).toBeInTheDocument();
  expect(within(banner).queryByRole("button", { name: /Restore from History/ })).toBeNull();
  // The Files tab says there are no files to show.
  expect(await screen.findByText("No files to show")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Open History" })).toBeNull();
  fireEvent.click(within(banner).getByRole("button", { name: "Delete skill…" }));
  expect(await screen.findByRole("dialog", { name: "Delete hello?" })).toBeInTheDocument();
});
