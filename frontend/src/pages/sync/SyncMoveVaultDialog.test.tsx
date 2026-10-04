// frontend/src/pages/sync/SyncMoveVaultDialog.test.tsx
//
// "Move the vault out of iCloud Drive" (6.4.19): From is where the files really
// are, To starts at the daemon's suggestion, Move vault sends the target, and a
// refusal (a target inside another cloud folder, say) shows in the dialog.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { ApiError } from "@/lib/api/errors";
import { acceptance } from "@/test/acceptance";
import { SyncMoveVaultDialog } from "./SyncMoveVaultDialog";
import { idleMutation, makeStatus } from "./syncTestKit";

vi.mock("@/lib/hooks/useSync", () => ({ useMoveVault: vi.fn() }));
vi.mock("@/components/FolderPickerField", () => ({
  FolderPickerField: ({
    value,
    onChange,
    inputId,
  }: {
    value: string | null;
    onChange: (p: string | null) => void;
    inputId: string;
  }) => <input id={inputId} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />,
}));
const toast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock("@/components/ui/toast", () => ({ useToast: () => ({ toast }) }));

const { useMoveVault } = await import("@/lib/hooks/useSync");
afterEach(() => vi.clearAllMocks());

const STATUS = makeStatus({
  synchroniser: "iCloud Drive",
  vault_path: "/Users/me/.coffer/vault",
  vault_real_path: "/Users/me/Library/Mobile Documents/Coffer",
  default_vault_path: "/Users/me/.coffer/vault",
});

function show(mutation = idleMutation()) {
  vi.mocked(useMoveVault).mockReturnValue(mutation as unknown as ReturnType<typeof useMoveVault>);
  const onOpenChange = vi.fn();
  render(<SyncMoveVaultDialog open onOpenChange={onOpenChange} status={STATUS} />);
  return { onOpenChange, dialog: within(screen.getByRole("dialog")) };
}

describe("SyncMoveVaultDialog", () => {
  acceptance("vault-sync", "the vault is moved out of a synchronised folder", () => {
    const mutate = vi.fn((_to: string, opts?: { onSuccess?: (r: { to: string }) => void }) =>
      opts?.onSuccess?.({ to: "/Users/me/.coffer/vault" }),
    );
    const { dialog, onOpenChange } = show(idleMutation({ mutate }));
    expect(dialog.getByText("Move the vault out of iCloud Drive")).toBeInTheDocument();
    expect(dialog.getByTestId("move-vault-from")).toHaveTextContent(
      "/Users/me/Library/Mobile Documents/Coffer",
    );
    expect(dialog.getByLabelText("To")).toHaveValue("/Users/me/.coffer/vault");
    expect(
      dialog.getByText("The old folder is left empty; delete it yourself."),
    ).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Move vault" }));
    expect(mutate).toHaveBeenCalledWith("/Users/me/.coffer/vault", expect.anything());
    expect(toast.success).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  test("a chosen folder replaces the suggestion, and a refusal is shown in the dialog", () => {
    const error = new ApiError("SYNC_VAULT_TARGET_IN_CLOUD", "inside iCloud Drive");
    const mutate = vi.fn();
    const { dialog } = show(idleMutation({ mutate, error }));
    fireEvent.change(dialog.getByLabelText("To"), { target: { value: "/Users/me/Dropbox/v" } });
    fireEvent.click(dialog.getByRole("button", { name: "Move vault" }));
    expect(mutate).toHaveBeenCalledWith("/Users/me/Dropbox/v", expect.anything());
    expect(dialog.getByRole("alert")).toHaveTextContent("Couldn’t move the vault");
  });
});
