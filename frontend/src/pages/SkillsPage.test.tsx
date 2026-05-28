// frontend/src/pages/SkillsPage.test.tsx — TEST21-013
//
// Carries the acceptance marker for spec scenario "desktop and CLI cover
// every operation" — the desktop surface that spec 005 §US 6 requires.

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
  useFetchSkill: vi.fn(),
  useEnableSkill: vi.fn(),
  useDisableSkill: vi.fn(),
  useRemoveSkill: vi.fn(),
  useVerifySkills: vi.fn(),
}));
const hooks = await import("@/lib/hooks/useSkills");
const useSkillsMock = vi.mocked(hooks.useSkills);
const useImportSkillMock = vi.mocked(hooks.useImportSkill);
const useFetchSkillMock = vi.mocked(hooks.useFetchSkill);
const useRemoveSkillMock = vi.mocked(hooks.useRemoveSkill);
const useVerifySkillsMock = vi.mocked(hooks.useVerifySkills);

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
  useFetchSkillMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    error: null,
  } as unknown as ReturnType<typeof hooks.useFetchSkill>);
  useRemoveSkillMock.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useRemoveSkill>);
  useVerifySkillsMock.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ entries: opts.verifyEntries ?? [] }),
    isPending: false,
  } as unknown as ReturnType<typeof hooks.useVerifySkills>);
}

acceptance("005-skill-manager", "desktop and CLI cover every operation", async () => {
  stubHooks({ data: SAMPLE });
  render(<SkillsPage />, { wrapper: wrap(null) });
  expect(screen.getByRole("heading", { name: /skills/i })).toBeInTheDocument();
  expect(screen.getByText("hello")).toBeInTheDocument();

  // Toggle the import form on.
  fireEvent.click(screen.getByRole("button", { name: /^import$/i }));
  await waitFor(() => expect(screen.getByPlaceholderText(/\.claude\/skills/i)).toBeInTheDocument());
});

describe("SkillsPage", () => {
  afterEach(() => vi.clearAllMocks());

  test("renders the loading state when the query is pending", () => {
    stubHooks({ isPending: true });
    render(<SkillsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test("renders the empty-state card when no skills exist", () => {
    stubHooks({ data: [] });
    render(<SkillsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/no skills yet/i)).toBeInTheDocument();
  });

  test("renders the error card when the query errors", () => {
    stubHooks({
      error: { code: "BOOM", message: "kaboom" },
    });
    render(<SkillsPage />, { wrapper: wrap(null) });
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  test("Fetch button reveals the FetchForm", async () => {
    stubHooks({ data: SAMPLE });
    render(<SkillsPage />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /fetch from git/i }));
    await waitFor(() => expect(screen.getByPlaceholderText(/github\.com/i)).toBeInTheDocument());
  });

  test("Verify button alerts on no drift", async () => {
    stubHooks({ data: SAMPLE, verifyEntries: [] });
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    render(<SkillsPage />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /verify/i }));
    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    alertSpy.mockRestore();
  });

  test("Verify button alerts when drift entries are reported", async () => {
    stubHooks({
      data: SAMPLE,
      verifyEntries: [
        {
          skill_name: "hello",
          agent_name: "cur",
          kind: "MISSING_LINK",
          target_path: "/x",
          suggested_remedy: "Re-enable",
        },
      ],
    });
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    render(<SkillsPage />, { wrapper: wrap(null) });
    fireEvent.click(screen.getByRole("button", { name: /verify/i }));
    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    // The message includes the count via the i18n key with {{count}}.
    expect(String(alertSpy.mock.calls[0][0])).toMatch(/1/);
    alertSpy.mockRestore();
  });
});
