// frontend/src/components/skills/SkillAddDialog.test.tsx
//
// The combined Add-skill dialog: two tabs ("Local folder" / "From Git"), each
// with its own form + mutation. Submitting either path calls the mutation and,
// on resolve, fires onCreated + closes the dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { SkillAddDialog } from "./SkillAddDialog";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useSkills", () => ({
  useImportSkill: vi.fn(),
  useFetchSkill: vi.fn(),
}));
const { useImportSkill, useFetchSkill } = await import("@/lib/hooks/useSkills");
const useImportSkillMock = vi.mocked(useImportSkill);
const useFetchSkillMock = vi.mocked(useFetchSkill);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

function stub(opts: {
  importAsync?: ReturnType<typeof vi.fn>;
  fetchAsync?: ReturnType<typeof vi.fn>;
  importError?: unknown;
  fetchError?: unknown;
}) {
  useImportSkillMock.mockReturnValue({
    mutateAsync: opts.importAsync ?? vi.fn().mockResolvedValue({}),
    isPending: false,
    error: opts.importError ?? null,
  } as unknown as ReturnType<typeof useImportSkill>);
  useFetchSkillMock.mockReturnValue({
    mutateAsync: opts.fetchAsync ?? vi.fn().mockResolvedValue({}),
    isPending: false,
    error: opts.fetchError ?? null,
  } as unknown as ReturnType<typeof useFetchSkill>);
}

describe("SkillAddDialog", () => {
  afterEach(() => vi.clearAllMocks());

  test("shows both tabs and the local-folder form by default", () => {
    stub({});
    render(<SkillAddDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByRole("tab", { name: /local folder/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /from git/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/\.claude\/skills/i)).toBeInTheDocument();
  });

  test("the local tab imports the path and fires onCreated + close", async () => {
    const importAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    const onOpenChange = vi.fn();
    stub({ importAsync });
    render(<SkillAddDialog open onOpenChange={onOpenChange} onCreated={onCreated} />, {
      wrapper: wrap(null),
    });
    fireEvent.change(screen.getByPlaceholderText(/\.claude\/skills/i), {
      target: { value: "/tmp/my-skill" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^import$/i }));
    await waitFor(() => expect(importAsync).toHaveBeenCalledWith({ path: "/tmp/my-skill" }));
    expect(onCreated).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("the Git tab fetches the repo and fires onCreated + close", async () => {
    const fetchAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    const onOpenChange = vi.fn();
    stub({ fetchAsync });
    render(<SkillAddDialog open onOpenChange={onOpenChange} onCreated={onCreated} />, {
      wrapper: wrap(null),
    });
    // Radix Tabs activate on pointer/mousedown (plain click is a no-op in jsdom).
    fireEvent.mouseDown(screen.getByRole("tab", { name: /from git/i }));
    const urlInput = await screen.findByPlaceholderText(/github\.com/i);
    fireEvent.change(urlInput, { target: { value: "https://example.com/repo" } });
    fireEvent.click(screen.getByRole("button", { name: /fetch from git/i }));
    await waitFor(() => expect(fetchAsync).toHaveBeenCalledTimes(1));
    expect(fetchAsync.mock.calls[0][0].git_url).toBe("https://example.com/repo");
    expect(fetchAsync.mock.calls[0][0].git_ref).toBe("main");
    expect(onCreated).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("surfaces the import error inline", () => {
    stub({ importError: new ApiError("INVALID_SKILL", "missing SKILL.md") });
    render(<SkillAddDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByText(/missing SKILL\.md|invalid/i)).toBeInTheDocument();
  });
});
