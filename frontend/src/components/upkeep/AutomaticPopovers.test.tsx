// frontend/src/components/upkeep/AutomaticPopovers.test.tsx
//
// The automatic-read schedule behind the ▾ of Memory's Update memory button (spec internal-engine
// "Show and change the memory passes on the Memory page"): it opens a popover
// whose edits write the aggregate and distil passes.
import { beforeEach, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { MemoryAutomaticPopover } from "@/components/memory/MemoryAutomaticPopover";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { InternalEngineConfig, UpkeepSetting } from "@/lib/api/internalEngine";
import { acceptance } from "@/test/acceptance";

const MINUTE = 60_000;
const at = (minutes: number) => new Date(Date.now() + minutes * MINUTE).toISOString();

let config: Partial<InternalEngineConfig> = {};
const setUpkeep = vi.fn();

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: config }),
  useSetUpkeep: () => ({ isPending: false, mutate: setUpkeep }),
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

acceptance("internal-engine", "the memory popover switches reading and distilling together", () => {
  config = {
    upkeep: {
      aggregate: pass({ last_pass_at: at(-14), next_pass_at: at(46) }),
      distil: pass({ default_interval_s: 21600 }),
    },
  };
  renderIt(<MemoryAutomaticPopover trigger={<button data-testid="memory-automatic">v</button>} />);
  const dialog = open("memory-automatic");
  expect(dialog).toHaveTextContent("Read memory automatically");
  expect(dialog).toHaveTextContent(/Last read 14m ago · next in 46m/);

  fireEvent.click(within(dialog).getByRole("switch", { name: "Read memory automatically" }));
  expect(setUpkeep).toHaveBeenCalledTimes(2);
  expect(setUpkeep).toHaveBeenCalledWith({ pass: "aggregate", enabled: false });
  expect(setUpkeep).toHaveBeenCalledWith({ pass: "distil", enabled: false });

  setUpkeep.mockClear();
  pickInterval(dialog, "30 minutes");
  expect(setUpkeep).toHaveBeenCalledTimes(1);
  expect(setUpkeep).toHaveBeenCalledWith({ pass: "aggregate", interval_s: 1800 });
});
