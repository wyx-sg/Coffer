// frontend/src/components/skills/SkillAddDialog.test.tsx
//
// The "Add skill" dialog: a single local-folder import form with its own
// mutation. The folder is PICKED via the FolderPicker (read-only display), not
// typed; submitting calls the mutation and, on resolve, fires onCreated +
// closes the dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { PropsWithChildren } from "react";
import { SkillAddDialog } from "./SkillAddDialog";
import { ApiError } from "@/lib/api/errors";

vi.mock("@/lib/hooks/useSkills", () => ({
  useImportSkill: vi.fn(),
}));
const { useImportSkill } = await import("@/lib/hooks/useSkills");
const useImportSkillMock = vi.mocked(useImportSkill);

// The read-only path field is filled by the FolderPicker, which on the web asks
// the daemon to open the native dialog (fsApi.pickFolder).
vi.mock("@/lib/api/fs", () => ({ fsApi: { browse: vi.fn(), pickFolder: vi.fn() } }));
const { fsApi } = await import("@/lib/api/fs");
const pickFolderMock = vi.mocked(fsApi.pickFolder);

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children ?? ui}</QueryClientProvider>
  );
}

function stub(opts: {
  importAsync?: ReturnType<typeof vi.fn>;
  importError?: unknown;
  reset?: ReturnType<typeof vi.fn>;
}) {
  useImportSkillMock.mockReturnValue({
    mutateAsync: opts.importAsync ?? vi.fn().mockResolvedValue({}),
    isPending: false,
    error: opts.importError ?? null,
    reset: opts.reset ?? vi.fn(),
  } as unknown as ReturnType<typeof useImportSkill>);
}

/** Pick a folder through the (mocked) native dialog and wait for it to land. */
async function pickFolder(path: string) {
  pickFolderMock.mockResolvedValue({ available: true, path });
  fireEvent.click(screen.getByRole("button", { name: /browse/i }));
  await waitFor(() => expect(screen.getByPlaceholderText(/\.claude\/skills/i)).toHaveValue(path));
}

describe("SkillAddDialog", () => {
  afterEach(() => vi.clearAllMocks());

  test("shows the local-folder form", () => {
    stub({});
    render(<SkillAddDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByPlaceholderText(/\.claude\/skills/i)).toBeInTheDocument();
  });

  test("offers a folder picker beside the path display (spec 005 FR-030)", () => {
    stub({});
    render(<SkillAddDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    // The shared FolderPicker's Browse button — native dialog on desktop, daemon
    // native dialog → in-app browser on web — so the skill folder is picked, not typed.
    expect(screen.getByRole("button", { name: /browse/i })).toBeInTheDocument();
  });

  test("imports the picked path and fires onCreated + close", async () => {
    const importAsync = vi.fn().mockResolvedValue({});
    const onCreated = vi.fn();
    const onOpenChange = vi.fn();
    stub({ importAsync });
    render(<SkillAddDialog open onOpenChange={onOpenChange} onCreated={onCreated} />, {
      wrapper: wrap(null),
    });

    await pickFolder("/tmp/my-skill");
    fireEvent.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(importAsync).toHaveBeenCalledWith({ path: "/tmp/my-skill" }));
    expect(onCreated).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("Import is disabled until a folder is picked", () => {
    stub({});
    render(<SkillAddDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
  });

  test("surfaces the import error inline", () => {
    stub({ importError: new ApiError("INVALID_SKILL", "missing SKILL.md") });
    render(<SkillAddDialog open onOpenChange={() => {}} onCreated={() => {}} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByText(/missing SKILL\.md|invalid/i)).toBeInTheDocument();
  });

  test("409 conflict shows replace-confirm; confirming retries with overwrite: true", async () => {
    const conflictError = new ApiError("RESOURCE_ALREADY_EXISTS", "already exists");
    // First call rejects with 409; second call succeeds.
    const importAsync = vi.fn().mockRejectedValueOnce(conflictError).mockResolvedValueOnce({});
    const reset = vi.fn();
    const onCreated = vi.fn();
    const onOpenChange = vi.fn();
    stub({ importAsync, reset });

    render(<SkillAddDialog open onOpenChange={onOpenChange} onCreated={onCreated} />, {
      wrapper: wrap(null),
    });

    // Pick a folder and submit.
    await pickFolder("/tmp/my-skill");
    fireEvent.click(screen.getByRole("button", { name: /^import$/i }));

    // Conflict banner appears with skill name derived from the path.
    await waitFor(() => expect(screen.getByText(/my-skill.*already exists/i)).toBeInTheDocument());

    // First import call was without overwrite.
    expect(importAsync).toHaveBeenNthCalledWith(1, { path: "/tmp/my-skill" });

    // Click the Replace button.
    fireEvent.click(screen.getByRole("button", { name: /replace/i }));

    // Second call includes overwrite: true and dialog closes.
    await waitFor(() => expect(importAsync).toHaveBeenCalledTimes(2));
    expect(importAsync).toHaveBeenNthCalledWith(2, {
      path: "/tmp/my-skill",
      overwrite: true,
    });
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
