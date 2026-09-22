// frontend/src/components/settings/CurationOwner.test.tsx
//
// The machine that runs curation, on Settings → Engine → Automatic upkeep.
//
// Four states, and the whole point of the row is that they read differently:
// "another machine has it" is fine and "a machine nobody claims has it" means
// curation happens NOWHERE — the switch above still says on, and no other
// surface in the product mentions it. A test that only asserted "some text
// about a machine appears" would pass with those two collapsed, so each case
// asserts what the other three would not say.
//
// The registry is stubbed rather than fetched, because the cases that matter
// are the ones a real vault makes hardest to produce: one with no registry at
// all, and an owner the registry has forgotten.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { CurationOwner } from "./CurationOwner";
import { TooltipProvider } from "@/components/ui/tooltip";

const mutate = vi.fn();

vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));
vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));
vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useSetCurationOwner: () => ({ mutate, isPending: false, error: null }),
}));

const { useMachines } = await import("@/lib/hooks/useMachines");
const { useSyncStatus } = await import("@/lib/hooks/useSync");

/** This machine, and the other machine in the registry. Ids and names never
 *  coincide, so an assertion about the NAME cannot be satisfied by the id. */
const HERE = "machine-here";
const THERE = "machine-there";

function machine(id: string, name: string, isSelf: boolean) {
  return {
    machine_id: id,
    name,
    os: "darwin",
    hostname: name,
    coffer_version: "0.5.0",
    last_converged_on: null,
    key_matches: true,
    agents: [],
    is_self: isSelf,
  };
}

const REGISTRY = [machine(HERE, "Laptop", true), machine(THERE, "Desktop", false)];

/** Pass [] for a vault that has never converged: it has no registry at all,
 *  and must not be told that makes its own owner a fault. */
function stub({
  machines = REGISTRY,
  selfId = HERE as string | null,
  pending = false,
}: { machines?: typeof REGISTRY; selfId?: string | null; pending?: boolean } = {}) {
  vi.mocked(useMachines).mockReturnValue({
    data: pending ? undefined : { machines },
    isPending: pending,
  } as unknown as ReturnType<typeof useMachines>);
  vi.mocked(useSyncStatus).mockReturnValue({
    data: pending ? undefined : { machine_id: selfId },
    isPending: pending,
  } as unknown as ReturnType<typeof useSyncStatus>);
}

function show(ownerId: string | null) {
  return render(
    <TooltipProvider>
      <CurationOwner ownerId={ownerId} />
    </TooltipProvider>,
  );
}

afterEach(() => vi.clearAllMocks());

describe("CurationOwner", () => {
  test("owned by this machine: says so, and offers nothing to take over", () => {
    stub();
    show(HERE);

    expect(screen.getByText(/curation runs here/i)).toBeInTheDocument();
    expect(screen.getByText("Laptop")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run curation on this machine/i })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("owned elsewhere: names the machine, and is not a fault", () => {
    // Its NAME, not its id — a settings page that prints a ULID has not
    // answered the question the reader came with.
    stub();
    show(THERE);

    expect(screen.getByText("Desktop")).toBeInTheDocument();
    expect(screen.getByText(/runs on Desktop/i)).toBeInTheDocument();
    expect(screen.queryByText(THERE)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: /run curation on this machine/i })).toBeEnabled();
  });

  test("owned by nobody: curation runs here, said as a note and not a fault", () => {
    // Unlike a channel, which fails closed. A vault that never named an owner
    // is a vault with one machine; being wrong costs a duplicated document.
    stub();
    show(null);

    expect(screen.getByText("Every machine")).toBeInTheDocument();
    expect(screen.getByText(/holding the same knowledge twice/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    // Nothing to clear, so nothing offers to.
    expect(screen.queryByRole("button", { name: "Clear owner" })).toBeNull();
  });

  test("owned by a machine nobody claims: a fault, told apart from 'runs elsewhere'", () => {
    // The state this row exists for. Curation is running on NO machine, the
    // switch above still reads on, and nothing else reports it.
    stub();
    show("machine-retired");

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/no machine in the registry claims/i);
    expect(alert).toHaveTextContent("machine-retired");
    // "Somewhere else" copy must not be what this reads as.
    expect(screen.queryByText(/runs on Desktop/i)).toBeNull();
    expect(screen.getByText(/Unknown machine \(machine-retired\)/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run curation on this machine/i })).toBeEnabled();
  });

  test("an empty registry is not a fault", () => {
    // The single-machine install has never converged and so has no registry;
    // it cannot be absent from one, and must not be told curation is dead.
    stub({ machines: [], selfId: HERE });
    show(HERE);

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("This machine")).toBeInTheDocument();
    expect(screen.getByText(/curation runs here/i)).toBeInTheDocument();
  });

  test("nothing is claimed while the registry is still loading", () => {
    // Before it lands, every owner id in the world looks unclaimed — this row
    // would accuse a healthy vault of the one fault it exists to report.
    stub({ pending: true });
    const { container } = show(THERE);

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(container.querySelector('[data-testid="curation-owner"]')).toBeNull();
  });

  test("taking over names THIS machine, by id", () => {
    stub();
    show(THERE);

    fireEvent.click(screen.getByRole("button", { name: /run curation on this machine/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith(HERE);
  });

  test("a machine with no id of its own cannot be named the owner", () => {
    stub({ selfId: null });
    show(THERE);

    expect(screen.getByRole("button", { name: /run curation on this machine/i })).toBeDisabled();
  });

  test("clearing asks first, then sends null", () => {
    // Clearing re-opens the defect the owner exists to close, so it goes
    // through the confirmation every destructive settings action uses.
    stub();
    show(THERE);

    fireEvent.click(screen.getByRole("button", { name: "Clear owner" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/every machine sharing this vault/i)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Clear owner" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toBeNull();
  });
});
