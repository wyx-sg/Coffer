// Settings → Engine → Automatic upkeep: the passes Coffer runs on its own.
//
// The point of the card is that they are visible and stoppable, so these
// assert exactly that — each pass is named with what it WRITES, the switch and
// the interval are independent, and an interval nobody chose is shown as the
// default rather than as a blank.
import { afterEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { UpkeepSettings } from "./UpkeepSettings";
import { acceptance } from "@/test/acceptance";
import type { InternalEngineConfig } from "@/lib/api/internalEngine";

const mutate = vi.fn();

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: vi.fn(),
  useSetUpkeep: () => ({ mutate, isPending: false }),
}));

const hooks = await import("@/lib/hooks/useInternalEngine");

const CONFIG: InternalEngineConfig = {
  model: "some-model",
  updated_at: "2026-09-16T00:00:00Z",
  upkeep: {
    aggregate: { enabled: true, interval_s: null, default_interval_s: 3600 },
    organise: { enabled: true, interval_s: 900, default_interval_s: 21600 },
    tidy: { enabled: false, interval_s: null, default_interval_s: 21600 },
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
    // The difference that matters between them: two rewrite derived files, one
    // rewrites the only copy of the user's own writing.
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByText(/reads your agents' own memory files/i)).toBeInTheDocument();
    expect(screen.getByText(/rewrites the derived digest/i)).toBeInTheDocument();
    expect(screen.getByText(/rewrites the knowledge files you wrote/i)).toBeInTheDocument();
    // ...and only that one is cautioned.
    expect(screen.getByText(/edits the only copy/i)).toBeInTheDocument();
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

  acceptance("internal-engine", "Settings → Engine shows and changes both halves", () => {
    // One pass per write: a body carrying all three would make every toggle a
    // chance to write back a stale copy of the other two.
    stub(CONFIG);
    render(<UpkeepSettings />);

    fireEvent.click(screen.getByRole("switch", { name: "Organise knowledge" }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith({ pass: "tidy", enabled: true });
  });

  test("the switch reflects that only the derived-file passes ship on", () => {
    stub(CONFIG);
    render(<UpkeepSettings />);

    expect(screen.getByRole("switch", { name: "Read from agents" })).toBeChecked();
    expect(screen.getByRole("switch", { name: "Organise knowledge" })).not.toBeChecked();
  });

  test("a pass this build does not know about is skipped, not rendered broken", () => {
    stub({ ...CONFIG, upkeep: { aggregate: CONFIG.upkeep!.aggregate } });
    render(<UpkeepSettings />);

    expect(screen.getByRole("switch", { name: "Read from agents" })).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Organise knowledge" })).toBeNull();
  });

  test("renders nothing rather than guessing while the config is loading", () => {
    stub(null);
    const { container } = render(<UpkeepSettings />);

    expect(within(container).queryAllByRole("switch")).toHaveLength(0);
  });
});
