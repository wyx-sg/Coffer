// Settings → Engine → Automatic upkeep: the passes Coffer runs on its own.
//
// The point of the card is that they are visible and stoppable, so these
// assert exactly that — each pass is named with what it WRITES, the switch and
// the interval are independent, and an interval nobody chose is shown as the
// default rather than as a blank.
//
// The third pass is `curate`, not `tidy`. It no longer rewrites the knowledge
// files the user wrote: it reads them and derives the documents agents read
// (spec knowledge FR-021), which is why it ships ON and why its note is about
// what switching it OFF costs.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { UpkeepSettings } from "./UpkeepSettings";
import type { InternalEngineConfig } from "@/lib/api/internalEngine";

const mutate = vi.fn();

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: vi.fn(),
  useSetUpkeep: () => ({ mutate, isPending: false }),
}));

const hooks = await import("@/lib/hooks/useInternalEngine");

const CURATE_SWITCH = "Derive documents from sources";

const CONFIG: InternalEngineConfig = {
  model: "some-model",
  updated_at: "2026-09-16T00:00:00Z",
  upkeep: {
    aggregate: { enabled: true, interval_s: null, default_interval_s: 3600 },
    organise: { enabled: true, interval_s: 900, default_interval_s: 21600 },
    // On, unlike the pass it replaced: curation is the only path from a source
    // to something an agent can read, so a vault where it never runs has an
    // empty topics lane forever.
    curate: { enabled: true, interval_s: null, default_interval_s: 21600 },
  },
};

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
    // The difference that matters between them: what each one puts on disk,
    // and — for curation — what it explicitly does not touch.
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByText(/reads your agents' own memory files/i)).toBeInTheDocument();
    expect(screen.getByText(/rewrites the derived digest/i)).toBeInTheDocument();
    expect(screen.getByText(/derives the documents your agents read/i)).toBeInTheDocument();
    expect(screen.getByText(/never changes a source/i)).toBeInTheDocument();
  });

  test("says what switching curation off costs", () => {
    // Not "this rewrites your files" — curation writes only the derived lane.
    // The consequence worth a warning is the opposite one: off, nothing an
    // agent reads is ever derived.
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByText(/the documents agents read stay empty/i)).toBeInTheDocument();
  });

  test("an interval nobody chose reads as the default, with its real value", () => {
    // A blank here would leave the reader unable to tell how often the pass
    // they are looking at actually runs.
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByText("Default (Every 1h)")).toBeInTheDocument();
  });

  test("a chosen interval is shown instead of the default", () => {
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByText("Every 15 min")).toBeInTheDocument();
  });

  test("toggling one pass sends that pass alone", () => {
    // One pass per write: a body carrying all three would make every toggle a
    // chance to write back a stale copy of the other two.
    stub(CONFIG);
    render(<UpkeepSettings />);

    fireEvent.click(screen.getByRole("switch", { name: CURATE_SWITCH }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith({ pass: "curate", enabled: false });
  });

  test("curation ships on, like the other derived-file passes", () => {
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByRole("switch", { name: "Read from agents" })).toBeChecked();
    expect(screen.getByRole("switch", { name: CURATE_SWITCH })).toBeChecked();
  });

  test("a switched-off pass reads as off", () => {
    stub({
      ...CONFIG,
      upkeep: { ...CONFIG.upkeep, curate: { ...CONFIG.upkeep!.curate, enabled: false } },
    });
    render(<UpkeepSettings />);

    expect(screen.getByRole("switch", { name: CURATE_SWITCH })).not.toBeChecked();
  });

  test("a pass this build does not know about is skipped, not rendered broken", () => {
    stub({ ...CONFIG, upkeep: { aggregate: CONFIG.upkeep!.aggregate } });
    render(<UpkeepSettings />);

    expect(screen.getByRole("switch", { name: "Read from agents" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: CURATE_SWITCH })).toBeNull();
  });

  test("renders nothing rather than guessing while the config is loading", () => {
    stub(null);
    const { container } = render(<UpkeepSettings />);

    expect(within(container).queryAllByRole("switch")).toHaveLength(0);
  });
});
