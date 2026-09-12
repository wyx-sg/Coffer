// frontend/src/components/skills/SkillsTable.test.tsx
//
// The skills list renders via the shared DataTable: rows navigate to the detail
// page on click, each row carries the three-state ScopeControl (the skill's
// reach: Disabled / Every agent / Selected agents — the same control the detail
// page mounts) + a Delete action (which opens a styled confirmation dialog — no
// window.confirm), a status filter narrows the rows by that same reach, and a
// checkbox column enables bulk Verify / Delete. Verify is library-wide
// maintenance, so it lives on the bulk bar only — never per row.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { SkillsTable } from "./SkillsTable";
import type { SkillOut } from "@/lib/api/skills";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

// SkillsTable's bulk actions mount SkillVerifyDialog, which calls
// useVerifySkills() unconditionally — stub it alongside the row hooks.
vi.mock("@/lib/hooks/useSkills", () => ({
  useRemoveSkill: vi.fn(),
  useVerifySkills: vi.fn(),
  useRepairSkillDrift: vi.fn(),
}));

// The status cell is ScopeControl, so the row now reaches the scope/agent/
// enable hooks. useResourceScope returns nothing on purpose — the rows must
// render from the list payload's `scope`, and one test asserts the hook was
// called with its query switched OFF (no GET per row).
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "cc" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useEnableResource: vi.fn(),
  useDisableResource: vi.fn(),
}));

const { useRemoveSkill, useVerifySkills, useRepairSkillDrift } =
  await import("@/lib/hooks/useSkills");
const { useResourceScope } = await import("@/lib/hooks/useScope");
const { useEnableResource, useDisableResource } = await import("@/lib/hooks/useResourceMutations");
const useRemoveSkillMock = vi.mocked(useRemoveSkill);
const useVerifySkillsMock = vi.mocked(useVerifySkills);
const useRepairSkillDriftMock = vi.mocked(useRepairSkillDrift);

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
  useVerifySkillsMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    data: { entries: [] },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useVerifySkills>);
  useRepairSkillDriftMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    data: undefined,
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
  } as unknown as ReturnType<typeof useRepairSkillDrift>);
  return removeMutate;
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

/** The <tr> carrying the named skill. */
function rowFor(name: string): HTMLElement {
  return screen.getByText(name).closest("tr") as HTMLElement;
}

// Open the status filter dropdown and click an option by its label. DataTable
// renders the filter combobox in its toolbar (first in DOM order) and the
// pagination page-size combobox after the table, so the status filter is first.
function selectStatus(optionName: string) {
  fireEvent.click(screen.getAllByRole("combobox")[0]);
  fireEvent.click(screen.getByRole("option", { name: optionName }));
}

const SAMPLE: SkillOut[] = [
  {
    name: "hello-skill",
    description: "Greets the user",
    source: { type: "local_import", original_path: "/tmp/hello" },
    enabled: true,
    scope: null,
    version_hash: "abc123def456",
    master_path: "/master/hello-skill",
    last_synced_from_source_at: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    bindings: [
      {
        agent_name: "cc",
        last_linked_at: "2026-05-22T00:00:00Z",
        last_link_path: "/home/u/.claude/skills/hello-skill",
        link_mode: "symlink",
      },
    ],
  },
  {
    name: "git-skill",
    description: "From a repo",
    source: { type: "local_import", original_path: "/tmp/git-skill" },
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
    name: "scoped-skill",
    description: "Only for cc",
    source: { type: "local_import", original_path: "/tmp/scoped" },
    enabled: true,
    scope: ["cc"],
    version_hash: "111222333444",
    master_path: "/master/scoped-skill",
    last_synced_from_source_at: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    bindings: [],
  },
];

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

  test("no row offers Verify; the bulk bar still does", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(within(rowFor("hello-skill")).queryByRole("button", { name: /verify/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /verify/i })).toBeNull();

    // Selecting rows reveals the bulk bar, which keeps the library-wide Verify.
    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    expect(screen.getByRole("button", { name: /verify/i })).toBeInTheDocument();
  });

  test("the status cell is the three-state scope control, not an on/off switch", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    expect(screen.queryByRole("switch")).toBeNull();
    const row = within(rowFor("hello-skill"));
    expect(row.getByTestId("scope-control")).toBeInTheDocument();
    expect(row.getByRole("button", { name: /every agent/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    // A scoped skill lands on "Selected agents"; a disabled one on "Disabled".
    expect(
      within(rowFor("scoped-skill")).getByRole("button", { name: /selected agents/i }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      within(rowFor("git-skill")).getByRole("button", { name: /^disabled$/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  test("each row's scope comes from the list payload — no per-row scope fetch", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    // Third argument is the query's `enabled` flag: false on every row, so a
    // list of N skills costs one request, not N.
    expect(vi.mocked(useResourceScope).mock.calls.length).toBeGreaterThan(0);
    for (const call of vi.mocked(useResourceScope).mock.calls) {
      expect(call[2]).toBe(false);
    }
  });

  test("the scope control drives enable/disable from the list", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    fireEvent.click(within(rowFor("hello-skill")).getByRole("button", { name: /^disabled$/i }));
    expect(disableMutate).toHaveBeenCalledWith({ kind: "skill", name: "hello-skill" });

    fireEvent.click(within(rowFor("git-skill")).getByRole("button", { name: /every agent/i }));
    expect(enableMutate).toHaveBeenCalledWith({ kind: "skill", name: "git-skill" });
  });

  test("clicking inside the scope control does not navigate to the detail page", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    fireEvent.click(within(rowFor("hello-skill")).getByRole("button", { name: /^disabled$/i }));
    fireEvent.click(
      within(rowFor("hello-skill")).getByRole("button", { name: /selected agents/i }),
    );
    expect(navigateMock).not.toHaveBeenCalled();

    // …while the row itself still navigates.
    fireEvent.click(screen.getByText("Greets the user"));
    expect(navigateMock).toHaveBeenCalledWith("/skills/hello-skill");
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

    selectStatus("Selected agents");
    expect(screen.getByText("scoped-skill")).toBeInTheDocument();
    expect(screen.queryByText("hello-skill")).toBeNull();
  });

  test("the delete action opens a styled dialog and confirming invokes remove", () => {
    const mutate = stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete hello-skill/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls[0][0]).toBe("hello-skill");
  });

  test("cancelling the delete dialog is a no-op", () => {
    const mutate = stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete hello-skill/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });
});
