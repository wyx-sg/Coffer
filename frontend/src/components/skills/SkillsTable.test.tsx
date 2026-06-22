// frontend/src/components/skills/SkillsTable.test.tsx
//
// The skills list renders via the shared DataTable: rows navigate to the detail
// page on click, each row carries Verify + Delete icon+text actions (Delete
// opens a styled confirmation dialog — no window.confirm), and a checkbox
// column enables bulk Verify / Delete.

import { afterEach, describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { SkillsTable } from "./SkillsTable";
import type { SkillOut } from "@/lib/api/skills";

// SkillsTable's per-row + bulk actions mount SkillVerifyDialog, which calls
// useVerifySkills() unconditionally — stub it alongside useRemoveSkill.
vi.mock("@/lib/hooks/useSkills", () => ({
  useRemoveSkill: vi.fn(),
  useVerifySkills: vi.fn(),
  useRepairSkillDrift: vi.fn(),
}));

const { useRemoveSkill, useVerifySkills, useRepairSkillDrift } = await import(
  "@/lib/hooks/useSkills"
);
const useRemoveSkillMock = vi.mocked(useRemoveSkill);
const useVerifySkillsMock = vi.mocked(useVerifySkills);
const useRepairSkillDriftMock = vi.mocked(useRepairSkillDrift);

function stubVerify() {
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
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const SAMPLE: SkillOut[] = [
  {
    name: "hello-skill",
    description: "Greets the user",
    source: { type: "local_import", original_path: "/tmp/hello" },
    enabled: true,
    version_hash: "abc123def456",
    master_path: "/master/hello-skill",
    last_synced_from_source_at: null,
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
    bindings: [
      {
        agent_name: "cc",
        enabled: true,
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
    enabled: true,
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
    useRemoveSkillMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    stubVerify();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByText("hello-skill")).toBeInTheDocument();
    expect(screen.getByText("git-skill")).toBeInTheDocument();
    // Source column hidden — its only value (local_import) must not render.
    expect(screen.queryByText("local_import")).not.toBeInTheDocument();
  });

  test("a search box is available; the source filter is hidden", () => {
    useRemoveSkillMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    stubVerify();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    // The source filter is hidden — its "All sources" trigger must not render.
    // (A combobox still exists: the pagination page-size select.)
    expect(screen.queryByText("All sources")).not.toBeInTheDocument();
  });

  test("a select-all + per-row checkbox column is rendered for bulk actions", () => {
    useRemoveSkillMock.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    stubVerify();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    // Select-all head checkbox + one per row.
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(2);
  });

  test("the delete action opens a styled dialog and confirming invokes remove", () => {
    const mutate = vi.fn();
    useRemoveSkillMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    stubVerify();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete hello-skill/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    expect(mutate).toHaveBeenCalled();
    expect(mutate.mock.calls[0][0]).toBe("hello-skill");
  });

  test("cancelling the delete dialog is a no-op", () => {
    const mutate = vi.fn();
    useRemoveSkillMock.mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof useRemoveSkill>);
    stubVerify();
    render(<SkillsTable skills={SAMPLE} />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /delete hello-skill/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(mutate).not.toHaveBeenCalled();
  });
});
