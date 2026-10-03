// frontend/src/pages/sync/SyncMachinesTab.test.tsx
//
// The registry table (6.4.24). Its cells carry claims that would be wrong if
// rendered naively, so each has a test: two machines of one name are both
// listed and keyed by id; "last seen" comes from the machine's own last
// round; the curation owner is tagged read-only; a different master key is
// flagged (and "no fingerprint yet" is not); Rename is only on this Mac's
// row, behind its dialog, and Retire only on the others — at once, with an
// Undo toast.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import type { Machine } from "@/lib/api/sync";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { idleMutation, makeMachine } from "./syncTestKit";

vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: vi.fn(),
  useRenameSelf: vi.fn(),
  useRetireMachine: vi.fn(),
  useRestoreMachine: vi.fn(),
}));
const toast = { info: vi.fn(), error: vi.fn(), success: vi.fn() };
vi.mock("@/components/ui/toast", () => ({ useToast: () => ({ toast }) }));
vi.mock("@/lib/hooks/useInternalEngine", () => ({ useInternalEngineConfig: vi.fn() }));

const { useMachines, useRenameSelf, useRetireMachine, useRestoreMachine } =
  await import("@/lib/hooks/useMachines");
const { useInternalEngineConfig } = await import("@/lib/hooks/useInternalEngine");
const mocked = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const renameMutate = vi.fn();
const retireMutate = vi.fn((_: string, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
const restoreMutate = vi.fn();

const LOCAL = "a3f21c9e4b7d2610";
const OTHER = "bb11cc22dd33ee44";

const machine = (over: Partial<Machine> = {}) =>
  makeMachine({ machine_id: LOCAL, name: "MacBook Pro", ...over });
const other = (over: Partial<Machine> = {}) =>
  machine({ machine_id: OTHER, name: "Mac mini", is_self: false, ...over });

function seed(machines: Machine[], curator: string | null = null) {
  mocked(useMachines).mockReturnValue({ data: { machines }, isPending: false });
  mocked(useInternalEngineConfig).mockReturnValue({ data: { curate_owner_machine_id: curator } });
  mocked(useRenameSelf).mockReturnValue(idleMutation({ mutate: renameMutate }));
  mocked(useRetireMachine).mockReturnValue(idleMutation({ mutate: retireMutate }));
  mocked(useRestoreMachine).mockReturnValue(idleMutation({ mutate: restoreMutate }));
}

const rowFor = (id: string) => within(screen.getByTestId(`machine-${id}`));
const openMenu = (id: string, name: string) =>
  fireEvent.click(rowFor(id).getByRole("button", { name: `More for ${name}` }));

afterEach(() => vi.clearAllMocks());

describe("SyncMachinesTab", () => {
  acceptance("vault-sync", "the machine registry shows every machine and cannot conflict", () => {
    // Two machines the user called the same thing: both are listed, each
    // keyed by its derived id, and the local one is marked.
    const minutesAgo = new Date(Date.now() - 12 * 60_000).toISOString();
    seed([
      machine({ name: "laptop", last_round_at: new Date().toISOString(), last_round: "pulled" }),
      other({ name: "laptop", last_round_at: minutesAgo, last_round: "pushed" }),
    ]);
    render(<SyncMachinesTab />);

    expect(rowFor(LOCAL).getByText("This Mac")).toBeInTheDocument();
    expect(rowFor(OTHER).queryByText("This Mac")).not.toBeInTheDocument();
    expect(rowFor(LOCAL).getByText("Now")).toBeInTheDocument();
    expect(rowFor(OTHER).getByText("12 minutes ago")).toBeInTheDocument();
    expect(rowFor(LOCAL).getByText(/· Pulled/i)).toBeInTheDocument();
    expect(rowFor(OTHER).getByText("laptop")).toHaveAttribute("title", OTHER);
  });

  test("a Mac not seen for weeks says when, in the warning tone", () => {
    const old = new Date(Date.now() - 39 * 86_400_000).toISOString();
    seed([other({ last_round_at: old, last_round: "pulled" })]);
    render(<SyncMachinesTab />);
    const cell = rowFor(OTHER).getByText(/39 days ago/);
    expect(cell).toHaveClass("text-warning");
  });

  test("a machine that never ran a round says so", () => {
    seed([machine({ last_round_at: null })]);
    render(<SyncMachinesTab />);
    expect(rowFor(LOCAL).getByText("Never")).toBeInTheDocument();
  });

  test("only the curation owner carries the read-only Runs curation tag", () => {
    seed([machine(), other()], OTHER);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).getByText("Runs curation")).toBeInTheDocument();
    expect(rowFor(LOCAL).queryByText("Runs curation")).not.toBeInTheDocument();
  });

  test("each agent is shown by its mark", () => {
    const agents = [
      { type: "claude_code", name: "claude-code", plugins: [] },
      { type: "codex", name: "codex", plugins: [] },
    ];
    seed([machine({ agents })]);
    render(<SyncMachinesTab />);
    expect(rowFor(LOCAL).getByRole("img", { name: /claude code/i })).toBeInTheDocument();
    expect(rowFor(LOCAL).getByRole("img", { name: /codex/i })).toBeInTheDocument();
  });

  acceptance("vault-sync", "a peer holding another master key is flagged", () => {
    seed([machine(), other({ key_matches: false })]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).getByText("Different master key")).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/cannot be decrypted here/),
    );
    expect(rowFor(LOCAL).queryByText("Different master key")).not.toBeInTheDocument();
  });

  test("an unpublished fingerprint is unknown, not a mismatch", () => {
    seed([other({ key_matches: null })]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).queryByText("Different master key")).not.toBeInTheDocument();
  });

  test("this Mac is renamed from its menu; other Macs offer no rename", () => {
    seed([machine(), other()]);
    render(<SyncMachinesTab />);
    openMenu(OTHER, "Mac mini");
    expect(screen.queryByRole("menuitem", { name: "Rename" })).not.toBeInTheDocument();

    openMenu(LOCAL, "MacBook Pro");
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText(/only the name in this list changes/i)).toBeInTheDocument();
    const rename = dialog.getByRole("button", { name: "Rename" });
    expect(rename).toBeDisabled();
    fireEvent.change(dialog.getByLabelText("Name"), { target: { value: "Workhorse" } });
    fireEvent.click(rename);
    expect(renameMutate).toHaveBeenCalledWith("Workhorse", expect.anything());
  });

  test("retiring is offered for other machines only, runs at once and can be undone", () => {
    seed([machine(), other({ coffer_version: "1.0.0" })]);
    render(<SyncMachinesTab />);
    openMenu(LOCAL, "MacBook Pro");
    expect(screen.queryByRole("menuitem", { name: "Retire" })).not.toBeInTheDocument();

    openMenu(OTHER, "Mac mini");
    fireEvent.click(screen.getByRole("menuitem", { name: "Retire" }));
    // No confirmation dialog: the registry entry is all it removes.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(retireMutate).toHaveBeenCalledWith(OTHER, expect.anything());
    expect(toast.info).toHaveBeenCalledWith("Retired Mac mini", { undo: expect.any(Function) });

    toast.info.mock.calls[0][1].undo();
    expect(restoreMutate).toHaveBeenCalledWith(OTHER, expect.anything());
  });

  test("an empty registry explains itself rather than showing an empty table", () => {
    seed([]);
    render(<SyncMachinesTab />);
    expect(screen.getByText(/no macs yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
