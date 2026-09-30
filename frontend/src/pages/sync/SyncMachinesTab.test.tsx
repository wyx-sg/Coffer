// frontend/src/pages/sync/SyncMachinesTab.test.tsx
//
// The registry table. Its columns carry claims that would be wrong if rendered
// naively, so each has a test: the id's first 8 characters (two machines can
// share a name), "last seen" from the machine's own last round, the agents it
// runs with their plugin counts, and the key ✓/✗ (✗ means that machine's
// secrets cannot be decrypted here, which is not "no fingerprint yet").
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { acceptance } from "@/test/acceptance";
import type { Machine } from "@/lib/api/sync";
import { formatDateTime } from "@/lib/utils";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { idleMutation, makeMachine } from "./syncTestKit";

vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: vi.fn(),
  useRenameSelf: vi.fn(),
  useRetireMachine: vi.fn(),
}));

const { useMachines, useRenameSelf, useRetireMachine } = await import("@/lib/hooks/useMachines");

const renameMutate = vi.fn();
const retireMutate = vi.fn();

const LOCAL = "a3f21c9e4b7d2610";
const OTHER = "bb11cc22dd33ee44";

const machine = (over: Partial<Machine> = {}) =>
  makeMachine({ machine_id: LOCAL, name: "laptop", ...over });

function seed(machines: Machine[]) {
  vi.mocked(useMachines).mockReturnValue({
    data: { machines },
    isPending: false,
  } as unknown as ReturnType<typeof useMachines>);
  vi.mocked(useRenameSelf).mockReturnValue(
    idleMutation({ mutate: renameMutate }) as unknown as ReturnType<typeof useRenameSelf>,
  );
  vi.mocked(useRetireMachine).mockReturnValue(
    idleMutation({ mutate: retireMutate }) as unknown as ReturnType<typeof useRetireMachine>,
  );
}

const rowFor = (id: string) => within(screen.getByTestId(`machine-${id}`));

afterEach(() => vi.clearAllMocks());

describe("SyncMachinesTab", () => {
  acceptance("vault-sync", "the machine registry shows every machine and cannot conflict", () => {
    // Two machines the user called the same thing: both are listed, the local
    // one is marked, and the derived id beside each name keeps them apart.
    seed([
      machine({ last_round_at: "2026-09-12T08:00:00Z", last_round: "pulled" }),
      machine({ machine_id: OTHER, is_self: false, last_round_at: "2026-09-11T08:00:00Z" }),
    ]);
    render(<SyncMachinesTab />);

    expect(rowFor(LOCAL).getByText("a3f21c9e")).toBeInTheDocument();
    expect(rowFor(OTHER).getByText("bb11cc22")).toBeInTheDocument();
    expect(rowFor(LOCAL).getByText(/this machine/i)).toBeInTheDocument();
    expect(rowFor(LOCAL).getByText(formatDateTime("2026-09-12T08:00:00Z"))).toBeInTheDocument();
    expect(rowFor(OTHER).getByText(formatDateTime("2026-09-11T08:00:00Z"))).toBeInTheDocument();
    expect(rowFor(LOCAL).getByText(/pulled/i)).toBeInTheDocument();
  });

  test("the local row's name is editable", () => {
    seed([machine()]);
    render(<SyncMachinesTab />);
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

  test("a machine that never ran a round says so", () => {
    seed([machine({ last_round_at: null })]);
    render(<SyncMachinesTab />);
    expect(rowFor(LOCAL).getByText(/never/i)).toBeInTheDocument();
  });

  test("each agent is listed with how many plugins it runs", () => {
    const plugin = { id: "p", name: "p", marketplace: null, enabled: true, version: null };
    seed([
      machine({
        agents: [{ type: "claude_code", name: "claude-code", plugins: [plugin, plugin] }],
      }),
    ]);
    render(<SyncMachinesTab />);
    expect(rowFor(LOCAL).getByText(/claude_code/)).toHaveTextContent(/2 plugins/);
  });

  test("an unpublished fingerprint is unknown, not a mismatch", () => {
    seed([machine({ machine_id: OTHER, is_self: false, key_matches: null, last_round: null })]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).queryByText(/cannot be decrypted here/i)).not.toBeInTheDocument();
  });

  test("retiring is offered for other machines only, and says what it leaves", () => {
    seed([machine(), machine({ machine_id: OTHER, name: "desktop", is_self: false })]);
    render(<SyncMachinesTab />);

    expect(rowFor(LOCAL).queryByRole("button", { name: /retire/i })).not.toBeInTheDocument();
    fireEvent.click(rowFor(OTHER).getByRole("button", { name: /retire/i }));

    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText(/nothing else is rewritten/i)).toBeInTheDocument();
    expect(dialog.getByText(/runs nowhere until you bind it to another/i)).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: /retire/i }));
    expect(retireMutate).toHaveBeenCalledWith(OTHER, expect.anything());
  });

  acceptance("vault-sync", "a peer holding another master key is flagged", () => {
    seed([
      machine(),
      machine({ machine_id: OTHER, name: "desktop", is_self: false, key_matches: false }),
    ]);
    render(<SyncMachinesTab />);
    expect(rowFor(OTHER).getByText(/cannot be decrypted here/i)).toBeInTheDocument();
    expect(rowFor(LOCAL).queryByText(/cannot be decrypted here/i)).not.toBeInTheDocument();
  });

  test("an empty registry explains itself rather than showing an empty table", () => {
    seed([]);
    render(<SyncMachinesTab />);
    expect(screen.getByText(/no machines yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
