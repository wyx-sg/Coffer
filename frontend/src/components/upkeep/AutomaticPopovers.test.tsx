// frontend/src/components/upkeep/AutomaticPopovers.test.tsx
//
// The automatic-sync schedule behind the ▾ of Memory's Sync now button (spec
// memory "Sync on an interval and on demand"): it opens a popover whose edits
// write the internal engine's one `memory_sync` pass.
import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { MemorySyncButton } from "@/components/memory/MemorySyncButton";
import { TooltipProvider } from "@/components/ui/tooltip";
import { acceptance } from "@/test/acceptance";
import type { InternalEngineConfig, UpkeepSetting } from "@/lib/api/internalEngine";

const MINUTE = 60_000;
const at = (minutes: number) => new Date(Date.now() + minutes * MINUTE).toISOString();

let config: Partial<InternalEngineConfig> = {};
const setUpkeep = vi.fn();
const syncNow = vi.fn();

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: config }),
  useSetUpkeep: () => ({ isPending: false, mutate: setUpkeep }),
}));
vi.mock("@/lib/hooks/useMemory", () => ({
  useSyncNow: () => ({ isPending: false, mutate: syncNow }),
}));

function pass(over: Partial<UpkeepSetting> = {}): UpkeepSetting {
  return {
    enabled: true,
    interval_s: null,
    default_interval_s: 3600,
    last_pass_at: null,
    next_pass_at: null,
    ...over,
  };
}

function renderIt(node: React.ReactNode) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function open(testId: string) {
  fireEvent.click(screen.getByTestId(testId));
  return screen.getByRole("dialog");
}

function pickInterval(dialog: HTMLElement, label: string) {
  fireEvent.keyDown(within(dialog).getByRole("combobox", { name: "Every" }), { key: "ArrowDown" });
  fireEvent.click(screen.getByRole("option", { name: label }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

acceptance("internal-engine", "the memory popover switches and times the one memory_sync pass", () => {
  config = { upkeep: { memory_sync: pass({ last_pass_at: at(-14), next_pass_at: at(46) }) } };
  renderIt(<MemorySyncButton running={false} />);
  const dialog = open("memory-automatic");
  expect(dialog).toHaveTextContent("Sync memory automatically");
  expect(dialog).toHaveTextContent(/Last synced 14m ago · next in 46m/);

  fireEvent.click(within(dialog).getByRole("switch", { name: "Sync memory automatically" }));
  expect(setUpkeep).toHaveBeenCalledTimes(1);
  expect(setUpkeep).toHaveBeenCalledWith({ pass: "memory_sync", enabled: false });

  setUpkeep.mockClear();
  pickInterval(dialog, "30 minutes");
  expect(setUpkeep).toHaveBeenCalledTimes(1);
  expect(setUpkeep).toHaveBeenCalledWith({ pass: "memory_sync", interval_s: 1800 });
});

test("Sync now syncs, and reads Syncing… while the daemon reports a sync running", () => {
  config = { upkeep: { memory_sync: pass() } };
  const { rerender } = renderIt(<MemorySyncButton running={false} />);
  fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
  expect(syncNow).toHaveBeenCalledTimes(1);
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <MemoryRouter>
          <MemorySyncButton running />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByRole("button", { name: "Syncing…" })).toBeDisabled();
});
