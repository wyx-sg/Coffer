// frontend/src/components/skills/SkillsTable.test.tsx
//
// The skills list renders via the shared DataTable: rows navigate to the detail
// page on click, each row carries ScopeControl (the skill's reach — the same
// control the detail page mounts) + a Delete action (which opens a styled
// confirmation dialog — no window.confirm), a status filter narrows the rows by
// that same reach, and a checkbox column enables the bulk bar: that same reach
// control applied to the whole selection, plus Delete. There is no Verify
// anywhere any more — the drift report kept its CLI and REST surfaces, but the
// button was never used.
//
// Reach is ONE button per row whose label states the reach ("Every agent" /
// "1 agent" / "Disabled"), opening a panel where Disabled / Every agent / Only
// selected agents are radio choices. It used to be those three as buttons side
// by side in the row. So these tests read the state off the button's TEXT, and
// change it by opening the panel and picking a radio out of the portal.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import { SkillsTable } from "./SkillsTable";
import type { SkillOut } from "@/lib/api/skills";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/lib/hooks/useSkills", () => ({
  useRemoveSkill: vi.fn(),
}));

// The status cell is ScopeControl, so the row now reaches the scope/agent/
// enable hooks. useResourceScope returns nothing on purpose — the rows must
// render from the list payload's `scope`, and one test asserts the hook was
// called with its query switched OFF (no GET per row).
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
// The agent vocabulary a scope is judged against is a list of UIDS with names
// hanging off them: ScopeControl compares `scope.agents` to `a.uid`, and the
// pick-list prints `a.name`. A stub carrying only one of the two would either
// make every scoped skill look dormant or make the panel unreadable.
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ uid: "u-cc", name: "cc" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
}));

const { useRemoveSkill } = await import("@/lib/hooks/useSkills");
const { useResourceScope } = await import("@/lib/hooks/useScope");
const { useEnableResource, useDisableResource } = await import("@/lib/hooks/useResourceMutations");
const useRemoveSkillMock = vi.mocked(useRemoveSkill);

const enableMutate = vi.fn();
const disableMutate = vi.fn();

function stubHooks(removeMutate = vi.fn()) {
  useRemoveSkillMock.mockReturnValue({
    mutate: removeMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveSkill>);
  vi.mocked(useEnableResource).mockReturnValue({
    mutate: enableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useEnableResource>);
  vi.mocked(useDisableResource).mockReturnValue({
    mutate: disableMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDisableResource>);
  return removeMutate;
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{children ?? ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}

/** The <tr> carrying the named skill. */
function rowFor(name: string): HTMLElement {
  return screen.getByText(name).closest("tr") as HTMLElement;
}

/** The row's ONE reach button — its text is the skill's current reach. */
function reachIn(name: string) {
  return within(within(rowFor(name)).getByTestId("scope-control")).getByRole("button");
}

/** The panel's choices are portalled out of the row, so they are queried from
 *  the whole screen rather than within the <tr>. */
const choice = (label: RegExp) => screen.getByRole("radio", { name: label });

// Open the status filter dropdown and click an option by its label. DataTable
// renders the filter combobox in its toolbar (first in DOM order) and the
// pagination page-size combobox after the table, so the status filter is first.
function selectStatus(optionName: string) {
  fireEvent.click(screen.getAllByRole("combobox")[0]);
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

// Every fixture carries BOTH identities, deliberately unlike each other: the
// uid is what the row navigates to and what a delete/enable/disable is
// addressed to, the name is what the reader sees. A fixture whose uid equalled
// its name would let a request built from the label pass these tests.
const SAMPLE: SkillOut[] = [
  {
    uid: "sk-7f31",
    name: "hello-skill",
    description: "Greets the user",
    source: { type: "local_import", original_path: "/tmp/hello" },
    builtin: false,
    enabled: true,
    scope: null,
    version_hash: "abc123def456",
    master_path: "/master/hello-skill",
    last_synced_from_source_at: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    bindings: [
      {
        agent_uid: "u-cc",
        agent_name: "cc",
        last_linked_at: "2026-05-22T00:00:00Z",
        last_link_path: "/home/u/.claude/skills/hello-skill",
        link_mode: "symlink",
      },
    ],
  },
  {
    uid: "sk-2b98",
    name: "git-skill",
    description: "From a repo",
    source: { type: "local_import", original_path: "/tmp/git-skill" },
    builtin: false,
    enabled: false,
    scope: null,
    version_hash: "999888777666",
    master_path: "/master/git-skill",
    last_synced_from_source_at: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    bindings: [],
  },
  {
    // Enabled but scoped: the state the old on/off switch could not express.
    // The scope names the agent's UID; the panel below still reads "cc".
    uid: "sk-c40d",
    name: "scoped-skill",
    description: "Only for cc",
    source: { type: "local_import", original_path: "/tmp/scoped" },
    builtin: false,
    enabled: true,
    scope: { agents: ["u-cc"] },
    version_hash: "111222333444",
    master_path: "/master/scoped-skill",
    last_synced_from_source_at: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    bindings: [],
  },
];

// Coffer's own generated skill. The UI reads the `builtin` FLAG, never the
// source discriminator — which is why the source here is the ordinary one the
// hand-written `SkillSource` union still models: nothing in this table looks at
// it, and a row is Coffer's because the daemon says so on its own field.
const BUILTIN: SkillOut = {
  uid: "sk-guide",
  name: "coffer-guide",
  description: "Coffer's own manual",
  source: { type: "local_import", original_path: "" },
  builtin: true,
  enabled: true,
  scope: null,
  version_hash: "aaabbbcccddd",
  master_path: "/master/coffer-guide",
  last_synced_from_source_at: null,
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
  bindings: [],
};

describe("SkillsTable", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders one row per skill; the source column is hidden", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("hello-skill")).toBeInTheDocument();
    expect(screen.getByText("git-skill")).toBeInTheDocument();
    // Source column hidden — its only value (local_import) must not render.
    expect(screen.queryByText("local_import")).not.toBeInTheDocument();
  });

  test("a search box is available; the source filter is hidden", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    // The source filter is hidden — its "All sources" trigger must not render.
    expect(screen.queryByText("All sources")).not.toBeInTheDocument();
  });

  test("a select-all + per-row checkbox column is rendered for bulk actions", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    // Select-all head checkbox + one per row.
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(2);
  });

  test("Verify is gone from the row AND from the bulk bar", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(within(rowFor("hello-skill")).queryByRole("button", { name: /verify/i })).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.queryByRole("button", { name: /verify/i })).toBeNull();
  });

  test("the bulk bar carries the same reach control the rows do", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    const bar = within(screen.getByTestId("bulk-reach-control"));
    // The button claims no state: a mixed selection has no single reach, so it
    // names the action instead of misreporting the rows.
    const trigger = bar.getByRole("button");
    expect(trigger).toHaveTextContent(/set reach/i);

    // …and for the same reason no choice in its panel starts out selected,
    // though all three the rows offer are there.
    fireEvent.click(trigger);
    for (const label of [/^disabled$/i, /every agent/i, /only selected agents/i]) {
      expect(choice(label)).not.toBeChecked();
    }
  });

  test("the status cell is the reach control, not an on/off switch", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    expect(screen.queryByRole("switch")).toBeNull();
    expect(within(rowFor("hello-skill")).getByTestId("scope-control")).toBeInTheDocument();
    // The three states an on/off switch could not express, each read straight
    // off the one button rather than by comparing three segments.
    expect(reachIn("hello-skill")).toHaveTextContent(/^every agent$/i);
    // A scoped skill counts the agents it reaches; a disabled one says so.
    expect(reachIn("scoped-skill")).toHaveTextContent(/^1 agent$/i);
    expect(reachIn("git-skill")).toHaveTextContent(/^disabled$/i);
  });

  test("each row's scope comes from the list payload — no per-row scope fetch", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    // The hook is `useResourceScope(uid, enabled)` — the kind segment is gone,
    // so the SECOND argument is the query's `enabled` flag: false on every row,
    // so a list of N skills costs one request, not N.
    expect(vi.mocked(useResourceScope).mock.calls.length).toBeGreaterThan(0);
    for (const call of vi.mocked(useResourceScope).mock.calls) {
      expect(call[1]).toBe(false);
    }
  });

  test("the scope control drives enable/disable from the list", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    // Each state is picked inside the row's panel; a whole-value choice closes
    // it and commits on the way out.
    // Picked by name off the screen, written by uid onto the wire.
    fireEvent.click(reachIn("hello-skill"));
    fireEvent.click(choice(/^disabled$/i));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "skill", uid: "sk-7f31" });

    fireEvent.click(reachIn("git-skill"));
    fireEvent.click(choice(/every agent/i));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "skill", uid: "sk-2b98" });
  });

  test("clicking inside the scope control does not navigate to the detail page", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    // Not the button that opens the panel, and not the choices inside it
    // either: the panel is portalled out of the row, but it is still a React
    // child of the cell, so without the cell's guard its clicks would reach the
    // row and navigate away mid-choice.
    fireEvent.click(reachIn("hello-skill"));
    fireEvent.click(choice(/only selected agents/i));
    fireEvent.click(within(screen.getByTestId("scope-agent-cc")).getByRole("checkbox"));
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(navigateMock).not.toHaveBeenCalled();

    // …while the row itself still navigates — to the uid, which is what the
    // detail route is keyed on now, not to the label the row prints.
    fireEvent.click(screen.getByText("Greets the user"));
    expect(navigateMock).toHaveBeenCalledWith("/skills/sk-7f31");
  });

  test("the status filter narrows the rows by reach", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    selectStatus("Disabled");
    expect(screen.queryByText("hello-skill")).toBeNull();
    expect(screen.getByText("git-skill")).toBeInTheDocument();

    selectStatus("Every agent");
    expect(screen.getByText("hello-skill")).toBeInTheDocument();
    expect(screen.queryByText("git-skill")).toBeNull();
    expect(screen.queryByText("scoped-skill")).toBeNull();

    selectStatus("Only selected agents");
    expect(screen.getByText("scoped-skill")).toBeInTheDocument();
    expect(screen.queryByText("hello-skill")).toBeNull();
  });

  test("the delete action opens a styled dialog and confirming invokes remove", () => {
    const mutate = stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    // Both halves of the split in one test: the action and the confirmation
    // name the skill (that is what the user is being asked about), and the
    // request that follows is addressed to the uid.
    fireEvent.click(screen.getByRole("button", { name: /delete hello-skill/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("hello-skill");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls[0][0]).toBe("sk-7f31");
  });

  test("cancelling the delete dialog is a no-op", () => {
    const mutate = stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete hello-skill/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });

  test("Coffer's own skill wears the Built-in badge; the user's skills do not", () => {
    stubHooks();
    render(<SkillsTable skills={[...SAMPLE, BUILTIN]} />, { wrapper: wrap(null) });

    expect(within(rowFor("coffer-guide")).getByTestId("skill-builtin-badge")).toHaveTextContent(
      /built-in/i,
    );
    // One badge in the whole table: it marks the exception, not every row.
    expect(screen.getAllByTestId("skill-builtin-badge")).toHaveLength(1);
    expect(within(rowFor("hello-skill")).queryByTestId("skill-builtin-badge")).toBeNull();
  });

  acceptance(
    "skill-manager",
    "the skills surface marks the built-in skill and offers no delete",
    () => {
      const mutate = stubHooks();
      render(<SkillsTable skills={[...SAMPLE, BUILTIN]} />, { wrapper: wrap(null) });

      // Marked as Coffer's, and the only row that is.
      expect(within(rowFor("coffer-guide")).getByTestId("skill-builtin-badge")).toBeInTheDocument();
      // Neither door to a delete is open: not the row's button, and not the
      // bulk bar, which cannot select the row in the first place.
      expect(screen.getByRole("button", { name: /delete coffer-guide/i })).toBeDisabled();
      expect(within(rowFor("coffer-guide")).queryByRole("checkbox")).toBeNull();
      // And reach is untouched — existence is Coffer's, reach is the owner's.
      expect(within(rowFor("coffer-guide")).getByTestId("scope-control")).toBeInTheDocument();
      expect(mutate).not.toHaveBeenCalled();
    },
  );

  test("a built-in skill's delete is disabled, and clicking it opens nothing", () => {
    const mutate = stubHooks();
    render(<SkillsTable skills={[...SAMPLE, BUILTIN]} />, { wrapper: wrap(null) });

    const del = screen.getByRole("button", { name: /delete coffer-guide/i });
    expect(del).toBeDisabled();
    fireEvent.click(del);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mutate).not.toHaveBeenCalled();

    // …while an ordinary skill's delete is untouched.
    expect(screen.getByRole("button", { name: /delete hello-skill/i })).toBeEnabled();
  });

  test("a built-in skill has no checkbox, so bulk delete cannot reach it", () => {
    stubHooks();
    render(<SkillsTable skills={[...SAMPLE, BUILTIN]} />, { wrapper: wrap(null) });

    expect(within(rowFor("coffer-guide")).queryByRole("checkbox")).toBeNull();
    expect(within(rowFor("hello-skill")).getByRole("checkbox")).toBeInTheDocument();

    // Select-all takes the three ordinary rows and leaves Coffer's own out of
    // the selection the bulk bar acts on.
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByText(/3 selected/i)).toBeInTheDocument();
  });
});
