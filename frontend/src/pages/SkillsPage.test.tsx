// frontend/src/pages/SkillsPage.test.tsx
//
// Carries the acceptance marker for spec scenario "desktop and CLI cover
// every operation" — the desktop surface that the 005-skill-manager spec §US 6
// requires. The page now mirrors AgentsPage: PageHeader + welcome/loading/
// error/grid, with the Add action opening a dialog. (Verification moved to
// per-row + bulk actions inside SkillsTable, covered by SkillsTable.test.tsx.)

import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";
import { SkillsPage } from "./SkillsPage";
import { acceptance } from "@/test/acceptance";
import type { SkillOut } from "@/lib/api/skills";

vi.mock("@/lib/hooks/useSkills", () => ({
  useSkills: vi.fn(),
  useImportSkill: vi.fn(),
  useEnableSkill: vi.fn(),
  useDisableSkill: vi.fn(),
  useRemoveSkill: vi.fn(),
  useVerifySkills: vi.fn(),
  useRepairSkillDrift: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useSkills");
const useSkillsMock = vi.mocked(hooks.useSkills);
const useImportSkillMock = vi.mocked(hooks.useImportSkill);
const useRemoveSkillMock = vi.mocked(hooks.useRemoveSkill);
const useVerifySkillsMock = vi.mocked(hooks.useVerifySkills);
const useRepairSkillDriftMock = vi.mocked(hooks.useRepairSkillDrift);

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
    name: "hello",
    description: "h",
    source: { type: "local_import", original_path: "/tmp/h" },
    enabled: true,
    version_hash: "x",
    master_path: "/master/hello",
    last_synced_from_source_at: null,
    created_at: "2026-05-26T00:00:00Z",
    updated_at: "2026-05-26T00:00:00Z",
    bindings: [],
  },
];

function stubHooks(opts: {
  data?: SkillOut[];
  isPending?: boolean;
  error?: unknown;
  verifyEntries?: unknown[];
}) {
  useSkillsMock.mockReturnValue({
    data: opts.data,
    isPending: opts.isPending ?? false,
    error: opts.error ?? null,
    refetch: vi.fn().mockResolvedValue({}),
  } as unknown as ReturnType<typeof hooks.useSkills>);
  useImportSkillMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useImportSkill>);
  useRemoveSkillMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useRemoveSkill>);
  useVerifySkillsMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    data: { entries: opts.verifyEntries ?? [] },
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useVerifySkills>);
  useRepairSkillDriftMock.mockReturnValue({
    mutate: vi.fn(),
    reset: vi.fn(),
    data: undefined,
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useRepairSkillDrift>);
}

acceptance("005-skill-manager", "desktop and CLI cover every operation", async () => {
  stubHooks({ data: SAMPLE });
  render(<SkillsPage />, { wrapper: wrap(null) });
  expect(screen.getByRole("heading", { name: /skills/i })).toBeInTheDocument();
  expect(screen.getByText("hello")).toBeInTheDocument();

  // The Add-skill button opens the combined dialog with the local-folder form.
  fireEvent.click(screen.getByRole("button", { name: /add skill/i }));
  await waitFor(() => expect(screen.getByPlaceholderText(/\.claude\/skills/i)).toBeInTheDocument());
});

describe("SkillsPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders the loading state when the query is pending", () => {
    stubHooks({ isPending: true });
    render(<SkillsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the welcome panel when no skills exist", () => {
    stubHooks({ data: [] });
    render(<SkillsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/manage your skills/i)).toBeInTheDocument();
    // The welcome panel carries the single Add call-to-action; no header
    // actions while empty.
    expect(screen.getByRole("button", { name: /add skill/i })).toBeInTheDocument();
  });

  test("renders the error card when the query errors", () => {
    stubHooks({ error: { code: "BOOM", message: "kaboom" } });
    render(<SkillsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  test("the header no longer carries a Verify action (moved into the table)", () => {
    stubHooks({ data: SAMPLE });
    render(<SkillsPage />, { wrapper: wrap(null) });
    // Only the per-row Verify buttons from SkillsTable remain; there is no
    // page-level Verify next to Add skill.
    expect(screen.getByRole("button", { name: /add skill/i })).toBeInTheDocument();
  });
});
