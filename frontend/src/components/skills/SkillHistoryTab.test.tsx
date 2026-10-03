// frontend/src/components/skills/SkillHistoryTab.test.tsx
// A skill's History tab (canvas 4.3.19, 4.3.20; spec vault-storage "Show,
// compare and restore any version of a vault file"): the master folder's
// versions newest first — what each did and "who · when" (You, Coffer or Git,
// never "Sync") — the chosen version's diff for each file it changed, and
// Restore this version…, which opens the 1060 review (What will happen, the
// files, "Restore N files"), sent as a folder restore, a refusal kept in the
// dialog with the primary turned Retry. The page is mounted the way the router
// mounts it; only the api modules are mocked.
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
    // A row says what was done, then "who · when"; the newest wears Current.
    expect(rows[0]).toHaveTextContent("Edited SKILL.md");
    expect(rows[0]).toHaveTextContent("You ·");
    expect(rows[0]).toHaveTextContent("Current");
    expect(rows[1]).toHaveTextContent("Changed 2 files");
    expect(rows[1]).toHaveTextContent("Claude Code ·");
    expect(vaultApi.history).toHaveBeenCalledWith("skills/hello/");
    // The list's header counts the versions.
    expect(screen.getByText("2", { selector: "span.text-text-subtle" })).toBeInTheDocument();
    // The current version is chosen, and it cannot be restored onto itself.
    expect(await screen.findByText("new line of skills/hello/SKILL.md")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /restore this version/i })).toBeNull();
    expect(screen.getByText(/This is the current version\./)).toBeInTheDocument();
  },
);

test("a version written by sync reads as Git, never as Sync", async () => {
  vi.mocked(vaultApi.history).mockResolvedValue({
    ...HISTORY,
    versions: [
      NEWEST,
      version({
        version: "e".repeat(40),
        writer: "sync",
        display_writer: "sync",
        summary: "Merge",
      }),
      version({
        version: "f".repeat(40),
        writer: "daemon",
        display_writer: "daemon",
        operation: "baseline",
        paths: [],
      }),
    ],
  });
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  const rows = within(list).getAllByRole("button");
  expect(rows[1]).toHaveTextContent("Git ·");
  expect(rows[2]).toHaveTextContent("Coffer ·");
  expect(list).not.toHaveTextContent("Sync");
});

test("choosing a version shows From and To, who made it, and every file it changed with its diff", async () => {
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  fireEvent.click(within(list).getAllByRole("button")[1]);
  const detail = await screen.findByRole("region", { name: "The chosen version" });
  expect(within(detail).getByText("From")).toBeInTheDocument();
  expect(within(detail).getByText("To")).toBeInTheDocument();
  // To is the chosen version; it is the oldest here, so From is the start.
  expect(within(detail).getByText("cccccc" + "c")).toBeInTheDocument();
  expect(within(detail).getByText("Start")).toBeInTheDocument();
  expect(
    within(detail).getByText(/Claude Code changed this skill’s files through Coffer\./),
  ).toBeInTheDocument();
  // Both files, each under its own header with its operation.
  expect(await within(detail).findByText("new line of skills/hello/SKILL.md")).toBeInTheDocument();
  expect(within(detail).getByText("new line of skills/hello/run.sh")).toBeInTheDocument();
  expect(within(detail).getByRole("region", { name: "Changes to run.sh" })).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole("button", { name: /restore this version…/i }));
    const dialog = await screen.findByRole("dialog");
    // The 1060 review: what will happen, the files the restore undoes, the primary naming the write.
    expect(dialog).toHaveTextContent(/Restore the version of/);
    expect(within(dialog).getByTestId("changes-heading")).toHaveTextContent("Changes · 1");
    expect(within(dialog).getByText("What will happen")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(/as a new version on top of today’s/);
    expect(vaultApi.restore).not.toHaveBeenCalled();
    // Newest version's SKILL.md edit, read the other way round.
    expect(vaultApi.diff).toHaveBeenCalledWith("skills/hello/SKILL.md", NEWEST.version);
    fireEvent.click(await within(dialog).findByRole("button", { name: "Restore 1 file" }));
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

test("the restore review shows the newer version's diff reversed", async () => {
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  fireEvent.click(within(list).getAllByRole("button")[1]);
  fireEvent.click(await screen.findByRole("button", { name: /restore this version…/i }));
  const dialog = await screen.findByRole("dialog");
  const diff = await within(dialog).findByRole("region", { name: "Changes to SKILL.md" });
  // The version added "new line…" and removed "old line"; undoing it does the opposite.
  const removed = diff.querySelector('[data-line="remove"]') as HTMLElement;
  const added = diff.querySelector('[data-line="add"]') as HTMLElement;
  expect(removed).toHaveTextContent("new line of skills/hello/SKILL.md");
  expect(added).toHaveTextContent("old line");
});

test("a refused restore stays in the dialog with the reason and the primary becomes Retry", async () => {
  vi.mocked(vaultApi.restore).mockRejectedValue(
    new ApiError("VAULT_FILE_STALE", "skills/hello/SKILL.md has an edit on disk"),
  );
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  fireEvent.click(within(list).getAllByRole("button")[1]);
  fireEvent.click(await screen.findByRole("button", { name: /restore this version…/i }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(await within(dialog).findByRole("button", { name: "Restore 1 file" }));
  expect(await within(dialog).findByRole("alert")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

test("a Cancel (ghost) closes the restore review without writing", async () => {
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  fireEvent.click(within(list).getAllByRole("button")[1]);
  fireEvent.click(await screen.findByRole("button", { name: /restore this version…/i }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(vaultApi.restore).not.toHaveBeenCalled();
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

test("the history is one card: versions on the left, the chosen version on the right", async () => {
  renderSkillsPage("/skills/hello/history");
  const list = await screen.findByRole("list", { name: "Versions" }, { timeout: 5_000 });
  const split = list.closest("div[class*='flex-row']") as HTMLElement;
  expect(within(split).getByRole("separator")).toHaveAttribute("aria-orientation", "vertical");
  const detail = split.querySelector("section") as HTMLElement;
  expect(detail).not.toBeNull();
  expect(split.contains(list) && !detail.contains(list)).toBe(true);
  expect(await within(detail).findByText("new line of skills/hello/SKILL.md")).toBeInTheDocument();
  // Choosing another version remounts the right half.
  fireEvent.click(within(list).getAllByRole("button")[1]);
  expect(await screen.findByText("new line of skills/hello/run.sh")).toBeInTheDocument();
});
