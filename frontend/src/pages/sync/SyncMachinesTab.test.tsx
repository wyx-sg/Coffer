// frontend/src/pages/sync/SyncMachinesTab.test.tsx
//
// The registry table. Three of its columns carry a claim that would be wrong
// if rendered naively, so each has a test: the id's first 8 characters (two
// machines can share a name), "last converged" as a DAY (an idle machine does
// not stamp every round), and the key ✓/✗ (✗ means that machine's credentials
// cannot be decrypted here, which is not the same as "no fingerprint yet").
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";

import type { Machine } from "@/lib/api/sync";
import { SyncMachinesTab } from "./SyncMachinesTab";

vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: vi.fn(),
  useRenameSelf: vi.fn(),
  useRetireMachine: vi.fn(),
}));
vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));

const { useMachines, useRenameSelf, useRetireMachine } = await import("@/lib/hooks/useMachines");
const { useSyncStatus } = await import("@/lib/hooks/useSync");

const renameMutate = vi.fn();
const retireMutate = vi.fn();

const LOCAL = "a3f21c9e4b7d2610";
const OTHER = "bb11cc22dd33ee44";

function machine(overrides: Partial<Machine> = {}): Machine {
  return {
    machine_id: LOCAL,
    name: "laptop",
    os: "Darwin",
    hostname: "mba.local",
    coffer_version: "0.5.0",
    last_converged_on: "2026-09-12",
    key_matches: true,
    agents: ["claude-code", "codex"],
    is_self: true,
    ...overrides,
  };
}

function seed(machines: Machine[], derived = true) {
  vi.mocked(useMachines).mockReturnValue({
    data: { machines },
    isPending: false,
  } as unknown as ReturnType<typeof useMachines>);
  vi.mocked(useSyncStatus).mockReturnValue({
    data: { machine_id: LOCAL, machine_id_is_derived: derived },
  } as unknown as ReturnType<typeof useSyncStatus>);
  vi.mocked(useRenameSelf).mockReturnValue({
    mutate: renameMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRenameSelf>);
  vi.mocked(useRetireMachine).mockReturnValue({
    mutate: retireMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRetireMachine>);
}

const rowFor = (id: string) => within(screen.getByTestId(`machine-${id}`));

afterEach(() => vi.clearAllMocks());

describe("SyncMachinesTab", () => {
  acceptance("vault-sync", "the machine registry shows every machine and cannot conflict", () => {
    // Two machines the user called the same thing: the table lists both with
    // their names, last converged day and key state, marks the local one, and
    // stays unambiguous because the derived id is shown alongside the name.
    seed([
      machine({ name: "laptop" }),
      machine({ machine_id: OTHER, name: "laptop", is_self: false, last_converged_on: "2026-09-11" }),
    ]);
    render(<SyncMachinesTab />);

    expect(rowFor(LOCAL).getByText("a3f21c9e")).toBeInTheDocument();
    expect(rowFor(OTHER).getByText("bb11cc22")).toBeInTheDocument();
    expect(rowFor(LOCAL).getByText(/this machine/i)).toBeInTheDocument();
    expect(rowFor(LOCAL).getByText("2026-09-12")).toBeInTheDocument();
    expect(rowFor(OTHER).getByText("2026-09-11")).toBeInTheDocument();
  });

  test("the local row is marked and its name is editable", () => {
    seed([machine()]);
    render(<SyncMachinesTab />);

    expect(rowFor(LOCAL).getByText(/this machine/i)).toBeInTheDocument();
    const input = rowFor(LOCAL).getByLabelText(/machine name/i);
    fireEvent.change(input, { target: { value: "workhorse" } });
    fireEvent.blur(input);
    expect(renameMutate).toHaveBeenCalledWith("workhorse");
  });

  test("another machine's name is not editable — a machine writes only its own descriptor", () => {
    seed([machine({ machine_id: OTHER, name: "desktop", is_self: false })]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).queryByLabelText(/machine name/i)).not.toBeInTheDocument();
    expect(rowFor(OTHER).getByText("desktop")).toBeInTheDocument();
  });

  test("last converged is labelled a day, not an instant", () => {
    seed([machine({ last_converged_on: "2026-09-12" })]);
    render(<SyncMachinesTab />);
    expect(rowFor(LOCAL).getByText("2026-09-12")).toBeInTheDocument();
    expect(screen.getByText(/running but idle/i)).toBeInTheDocument();
  });

  test("a machine that never converged says so", () => {
    seed([machine({ last_converged_on: null })]);
    render(<SyncMachinesTab />);
    expect(rowFor(LOCAL).getByText(/never/i)).toBeInTheDocument();
  });

  test("a key mismatch says the credentials cannot be decrypted here", () => {
    seed([machine({ machine_id: OTHER, is_self: false, key_matches: false })]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).getByText(/cannot be decrypted here/i)).toBeInTheDocument();
  });

  test("an unpublished fingerprint is unknown, not a mismatch", () => {
    seed([machine({ machine_id: OTHER, is_self: false, key_matches: null })]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).queryByText(/cannot be decrypted here/i)).not.toBeInTheDocument();
    expect(rowFor(OTHER).getByText("—")).toBeInTheDocument();
  });

  test("retiring is offered for other machines only, and touches nothing else", () => {
    // Retiring used to rewrite every scope that named the machine, and the
    // dialog had to warn about it. Reach is set per machine now and no scope
    // can name one, so the dialog's job is the opposite: to say that removing
    // the descriptor is the whole of the change.
    seed([machine(), machine({ machine_id: OTHER, name: "desktop", is_self: false })]);
    render(<SyncMachinesTab />);

    expect(rowFor(LOCAL).queryByRole("button", { name: /retire/i })).not.toBeInTheDocument();
    fireEvent.click(rowFor(OTHER).getByRole("button", { name: /retire/i }));

    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText(/nothing else in the vault changes/i)).toBeInTheDocument();
    expect(dialog.queryByText(/scope/i)).not.toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: /retire/i }));
    expect(retireMutate).toHaveBeenCalledWith(OTHER, expect.anything());
  });

  test("a non-derived machine id warns that deleting ~/.coffer makes a new machine", () => {
    seed([machine()], false);
    render(<SyncMachinesTab />);
    expect(screen.getByTestId("machine-id-not-derived")).toHaveTextContent(/new machine/i);
  });

  test("a derived machine id raises no such note", () => {
    seed([machine()], true);
    render(<SyncMachinesTab />);
    expect(screen.queryByTestId("machine-id-not-derived")).not.toBeInTheDocument();
  });

  test("an empty registry explains itself rather than showing an empty table", () => {
    seed([]);
    render(<SyncMachinesTab />);
    expect(screen.getByText(/no machines yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
