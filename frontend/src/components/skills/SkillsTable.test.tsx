// frontend/src/components/skills/SkillsTable.test.tsx
//
// The skills list renders via the shared DataTable: rows navigate to the detail
// page on click, each row carries an enable/disable Switch (the skill's own
// enabled flag) + a Delete action (which opens a styled confirmation dialog —
// no window.confirm), a status filter narrows the rows, and a checkbox column
// enables bulk Verify / Delete. Verify is library-wide maintenance, so it lives
// on the bulk bar only — never per row.

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
  useSetSkillEnabled: vi.fn(),
}));

const { useRemoveSkill, useVerifySkills, useRepairSkillDrift, useSetSkillEnabled } =
  await import("@/lib/hooks/useSkills");
const useRemoveSkillMock = vi.mocked(useRemoveSkill);
const useVerifySkillsMock = vi.mocked(useVerifySkills);
const useRepairSkillDriftMock = vi.mocked(useRepairSkillDrift);
const useSetSkillEnabledMock = vi.mocked(useSetSkillEnabled);

const enableMutate = vi.fn();
const disableMutate = vi.fn();

function stubHooks(removeMutate = vi.fn()) {
  useRemoveSkillMock.mockReturnValue({
    mutate: removeMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRemoveSkill>);
  useSetSkillEnabledMock.mockReturnValue({
    enable: { mutate: enableMutate, isPending: false },
    disable: { mutate: disableMutate, isPending: false },
  } as unknown as ReturnType<typeof useSetSkillEnabled>);
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

  test("the status switch reflects `enabled` and toggles the skill resource", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    const on = within(rowFor("hello-skill")).getByRole("switch");
    const off = within(rowFor("git-skill")).getByRole("switch");
    expect(on).toBeChecked();
    expect(off).not.toBeChecked();

    fireEvent.click(on);
    expect(disableMutate).toHaveBeenCalledWith({ kind: "skill", name: "hello-skill" });
    fireEvent.click(off);
    expect(enableMutate).toHaveBeenCalledWith({ kind: "skill", name: "git-skill" });
  });

  test("clicking the status switch does not navigate to the detail page", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    fireEvent.click(within(rowFor("hello-skill")).getByRole("switch"));
    expect(navigateMock).not.toHaveBeenCalled();

    // …while the row itself still navigates.
    fireEvent.click(screen.getByText("Greets the user"));
    expect(navigateMock).toHaveBeenCalledWith("/skills/hello-skill");
  });

  test("the status filter narrows the rows", () => {
    stubHooks();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });

    selectStatus("Disabled");
    expect(screen.queryByText("hello-skill")).toBeNull();
    expect(screen.getByText("git-skill")).toBeInTheDocument();

    selectStatus("Enabled");
    expect(screen.getByText("hello-skill")).toBeInTheDocument();
    expect(screen.queryByText("git-skill")).toBeNull();
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
