// frontend/src/components/skills/SkillHistoryTab.test.tsx
// A skill's History tab (spec vault-storage "Show, compare and restore any
// version of a vault file"): the master folder's versions newest first with
// who wrote each and when, the chosen version's diff for each file it
// changed, and Restore this version — confirmed first, sent as a folder
// restore, a refusal shown in the dialog. The page is mounted the way the
// router mounts it; only the api modules are mocked.
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import type { VaultHistoryOut, VaultVersionOut } from "@/lib/api/vault";
import { acceptance } from "@/test/acceptance";
import { BUILTIN_SKILL, makeSkill, renderSkillsPage } from "@/test/skillsPageKit";

const h = vi.hoisted(() => ({ skills: [] as SkillOut[] }));

vi.mock("@/lib/api/skills", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/skills")>()),
  skillsApi: {
    list: vi.fn(async () => ({ items: h.skills })),
    filesTree: vi.fn(),
    fileContent: vi.fn(),
    verify: vi.fn(),
  },
}));
vi.mock("@/lib/api/agents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/agents")>()),
  agentsApi: { list: vi.fn(async () => ({ items: [] })) },
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getApiClient: () => ({ GET: async () => ({ data: { resources: [] }, error: undefined }) }),
}));
vi.mock("@/lib/api/vault", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/vault")>()),
  vaultApi: { history: vi.fn(), diff: vi.fn(), restore: vi.fn() },
}));

const { vaultApi } = await import("@/lib/api/vault");

function version(over: Partial<VaultVersionOut>): VaultVersionOut {
  return {
    version: "a".repeat(40),
    time: "2026-09-30T08:00:00Z",
    writer: "user",
    display_writer: "user",
    actor: "ui",
    machine: "m1",
    summary: "Edit hello/SKILL.md",
    operation: "edit",
    restored_from: null,
    removed: false,
    paths: [{ path: "skills/hello/SKILL.md", status: "modified", added: 1, removed: 1 }],
    ...over,
  };
}

const NEWEST = version({ version: "b".repeat(40) });
const OLDER = version({
  version: "c".repeat(40),
  time: "2026-09-29T08:00:00Z",
  writer: "agent",
  display_writer: "agent:claude_code",
  paths: [
    { path: "skills/hello/SKILL.md", status: "modified", added: 2, removed: 0 },
    { path: "skills/hello/run.sh", status: "added", added: 1, removed: 0 },
  ],
});
const HISTORY: VaultHistoryOut = {
  path: "skills/hello/",
  versions: [NEWEST, OLDER],
  next_cursor: null,
};

beforeEach(() => {
  h.skills = [makeSkill()];
  vi.mocked(vaultApi.history).mockResolvedValue(HISTORY);
  vi.mocked(vaultApi.diff).mockImplementation(async (path, v) => ({
    path,
    version: v,
    status: "modified",
    diff: `--- a/${path}\n+++ b/${path}\n@@ -1 +1 @@\n-old line\n+new line of ${path}\n`,
    added: 1,
    removed: 1,
  }));
});
afterEach(() => vi.clearAllMocks());

acceptance(
  "skill-manager",
  "the history tab lists the folder's versions with their writers",
  async () => {
    renderSkillsPage("/skills/hello/history");
    const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
    const rows = within(list).getAllByRole("button");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("You");
    expect(rows[0]).toHaveTextContent("Current");
    expect(rows[1]).toHaveTextContent("Claude Code");
    expect(rows[1]).toHaveTextContent("2 files changed");
    expect(vaultApi.history).toHaveBeenCalledWith("skills/hello/");
    // The current version is chosen, and it cannot be restored onto itself.
    expect(await screen.findByText("new line of skills/hello/SKILL.md")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /restore this version/i })).toBeNull();
  },
);

test("choosing a version lists its changed files and shows the picked one's diff", async () => {
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  fireEvent.click(within(list).getAllByRole("button")[1]);
  expect(await screen.findByTestId("skill-version-file-run.sh")).toHaveTextContent("added");
  fireEvent.click(screen.getByTestId("skill-version-file-run.sh"));
  expect(await screen.findByText("new line of skills/hello/run.sh")).toBeInTheDocument();
  expect(vaultApi.diff).toHaveBeenCalledWith("skills/hello/run.sh", OLDER.version);
});

acceptance(
  "skill-manager",
  "restoring a version asks first and restores the whole folder",
  async () => {
    vi.mocked(vaultApi.restore).mockResolvedValue({
      path: "skills/hello/",
      version: "d".repeat(40),
      restored_from: OLDER.version,
      paths: ["skills/hello/SKILL.md"],
    });
    renderSkillsPage("/skills/hello/history");
    const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
    fireEvent.click(within(list).getAllByRole("button")[1]);
    fireEvent.click(await screen.findByRole("button", { name: /restore this version/i }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/files added since are removed/i);
    fireEvent.click(within(dialog).getByRole("button", { name: /restore this version/i }));
    await waitFor(() =>
      expect(vaultApi.restore).toHaveBeenCalledWith({
        path: "skills/hello/",
        version: OLDER.version,
        expected_fingerprint: null,
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  },
);

test("a refused restore stays in the dialog with the reason", async () => {
  vi.mocked(vaultApi.restore).mockRejectedValue(
    new ApiError("VAULT_FILE_STALE", "skills/hello/SKILL.md has an edit on disk"),
  );
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  fireEvent.click(within(list).getAllByRole("button")[1]);
  fireEvent.click(await screen.findByRole("button", { name: /restore this version/i }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: /restore this version/i }));
  expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

acceptance("skill-manager", "the history tab says versions are not recorded yet", async () => {
  vi.mocked(vaultApi.history).mockResolvedValue({ ...HISTORY, versions: [] });
  renderSkillsPage("/skills/hello/history");
  expect(await screen.findByText("No versions yet", {}, { timeout: 5_000 })).toBeInTheDocument();
});

acceptance("skill-manager", "Coffer's own skill has no history", async () => {
  h.skills = [BUILTIN_SKILL];
  renderSkillsPage(`/skills/${BUILTIN_SKILL.name}/history`);
  expect(
    await screen.findByText("Coffer’s own skill has no history", {}, { timeout: 5_000 }),
  ).toBeInTheDocument();
  expect(vaultApi.history).not.toHaveBeenCalled();
});

test("the history is split: versions on the left, the chosen version's diff on the right", async () => {
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  const split0 = list.closest("div[class*='flex-row']") as HTMLElement;
  expect(within(split0).getByRole("separator")).toHaveAttribute("aria-orientation", "vertical");
  const split = list.closest("div[class*='flex-row']") as HTMLElement;
  const detail = split.querySelector("section") as HTMLElement;
  expect(detail).not.toBeNull();
  expect(split.contains(list) && !detail.contains(list)).toBe(true);
  // The newest version's first file is on screen; picking the older one changes it.
  expect(await within(detail).findByText("new line of skills/hello/SKILL.md")).toBeInTheDocument();
  fireEvent.click(within(list).getAllByRole("button")[1]);
  fireEvent.click(await screen.findByTestId("skill-version-file-run.sh"));
  expect(await screen.findByText("new line of skills/hello/run.sh")).toBeInTheDocument();
});
