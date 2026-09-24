// Settings → Coffer's model → Automatic upkeep: the passes Coffer runs on its own.
//
// The point of the card is that they are visible and stoppable, so these
// assert exactly that — each pass is named with what it WRITES, the switch and
// the interval are independent, and an interval nobody chose is shown as the
// default rather than as a blank.
//
// The third pass is `curate`: it merges new material into a collection's
// documents and carries a person's edit through the rest (spec knowledge
// "Curate through a fenced four-tool pass"), which is why it ships ON and why its note is about
// what switching it OFF costs.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { UpkeepSettings } from "./UpkeepSettings";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { InternalEngineConfig } from "@/lib/api/internalEngine";

const mutate = vi.fn();
const setOwner = vi.fn();

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: vi.fn(),
  useSetUpkeep: () => ({ mutate, isPending: false }),
  useSetCurationOwner: () => ({ mutate: setOwner, isPending: false, error: null }),
}));
// Curation's row carries the machine that owns the pass, which joins the
// binding against the registry and this machine's id; both are stubbed so the
// row renders the same way on every run.
vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: () => ({
    data: {
      machines: [
        {
          machine_id: "machine-here",
          name: "Laptop",
          os: "darwin",
          hostname: "laptop",
          coffer_version: "0.5.0",
          last_converged_on: null,
          key_matches: true,
          agents: [],
          is_self: true,
        },
      ],
    },
    isPending: false,
  }),
  useThisMachineId: () => ({ machineId: "machine-here", isPending: false }),
}));

const hooks = await import("@/lib/hooks/useInternalEngine");

const CURATE_SWITCH = "Merge new knowledge into documents";

const CONFIG: InternalEngineConfig = {
  model: "some-model",
  updated_at: "2026-09-16T00:00:00Z",
  upkeep: {
    aggregate: { enabled: true, interval_s: null, default_interval_s: 3600 },
    distil: { enabled: true, interval_s: 900, default_interval_s: 21600 },
    // On: curation is what merges new material into the documents an agent
    // reads, so a vault where it never runs leaves that material unread.
    curate: { enabled: true, interval_s: null, default_interval_s: 21600 },
  },
  // The machine allowed to run curation — this one, in the fixture, which is
  // the state that says nothing is wrong.
  curate_owner_machine_id: "machine-here",
  default_model_timeout_s: 60,
};

/** The card under one TooltipProvider, which `Layout` mounts in the app: the
 *  curation-owner row hangs the reason a take-over is or is not possible off a
 *  Tooltip, and Radix has no provider of its own to fall back to. */
function renderCard() {
  return render(
    <TooltipProvider>
      <UpkeepSettings />
    </TooltipProvider>,
  );
}

// Takes the config explicitly: `stub(undefined)` would fall back to the
// default parameter and quietly stub the loaded config instead of the loading
// state — which is exactly the mistake that made the loading test pass for the
// wrong reason.
function stub(config: InternalEngineConfig | null) {
  vi.mocked(hooks.useInternalEngineConfig).mockReturnValue({
    data: config ?? undefined,
  } as unknown as ReturnType<typeof hooks.useInternalEngineConfig>);
}

afterEach(() => vi.clearAllMocks());

describe("UpkeepSettings", () => {
  test("names every pass by what it actually writes", () => {
    // The difference that matters between them: what each one puts on disk.
    stub(CONFIG);
    renderCard();

    expect(screen.getByText(/reads your agents' own memory files/i)).toBeInTheDocument();
    expect(screen.getByText(/turns the entries read from your agents into/i)).toBeInTheDocument();
    expect(screen.getByText(/merges new material/i)).toBeInTheDocument();
    expect(screen.getByText(/carries a document you edited through/i)).toBeInTheDocument();
  });

  test("says what switching curation off costs", () => {
    // The consequence worth a warning: off, new material waits unmerged and an
    // edit is not carried through.
    stub(CONFIG);
    renderCard();

    expect(screen.getByText(/new material waits unmerged/i)).toBeInTheDocument();
  });

  test("an interval nobody chose reads as the default, with its real value", () => {
    // A blank here would leave the reader unable to tell how often the pass
    // they are looking at actually runs.
    stub(CONFIG);
    renderCard();

    expect(screen.getByText("Default (Every 1h)")).toBeInTheDocument();
  });

  test("a chosen interval is shown instead of the default", () => {
    stub(CONFIG);
    renderCard();

    expect(screen.getByText("Every 15 min")).toBeInTheDocument();
  });

  test("toggling one pass sends that pass alone", () => {
    // One pass per write: a body carrying all three would make every toggle a
    // chance to write back a stale copy of the other two.
    stub(CONFIG);
    renderCard();

    fireEvent.click(screen.getByRole("switch", { name: CURATE_SWITCH }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith({ pass: "curate", enabled: false });
  });

  test("curation ships on, like the other derived-file passes", () => {
    stub(CONFIG);
    renderCard();

    expect(screen.getByRole("switch", { name: "Read from agents" })).toBeChecked();
    expect(screen.getByRole("switch", { name: CURATE_SWITCH })).toBeChecked();
  });

  test("a switched-off pass reads as off", () => {
    stub({
      ...CONFIG,
      upkeep: { ...CONFIG.upkeep, curate: { ...CONFIG.upkeep!.curate, enabled: false } },
    });
    renderCard();

    expect(screen.getByRole("switch", { name: CURATE_SWITCH })).not.toBeChecked();
  });

  test("a pass this build does not know about is skipped, not rendered broken", () => {
    stub({ ...CONFIG, upkeep: { aggregate: CONFIG.upkeep!.aggregate } });
    renderCard();

    expect(screen.getByRole("switch", { name: "Read from agents" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: CURATE_SWITCH })).toBeNull();
  });

  test("only curation says which machine runs it", () => {
    // The other two passes read and write this machine's own files; only
    // curation writes documents a second machine would write differently,
    // so only curation names an owner.
    stub(CONFIG);
    renderCard();

    expect(screen.getAllByTestId("curation-owner")).toHaveLength(1);
    expect(screen.getByText(/curation runs here/i)).toBeInTheDocument();
  });

  test("an owner the registry has forgotten reads as a fault on this card", () => {
    // The pass is switched on, its interval still reads every six hours, and
    // it is running on no machine at all. This row is the only thing that says
    // so, which is why it is asserted through the card and not only the unit.
    stub({ ...CONFIG, curate_owner_machine_id: "machine-retired" });
    renderCard();

    expect(screen.getByRole("switch", { name: CURATE_SWITCH })).toBeChecked();
    expect(screen.getByRole("alert")).toHaveTextContent(/no machine in the registry claims/i);
  });

  test("renders nothing rather than guessing while the config is loading", () => {
    stub(null);
    const { container } = renderCard();

    expect(within(container).queryAllByRole("switch")).toHaveLength(0);
  });
});
