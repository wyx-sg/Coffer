// frontend/src/components/upkeep/AutomaticPopovers.test.tsx
//
// The Automatic controls in the Knowledge and Memory headers (spec
// internal-engine "Show and change the unattended passes on the pages they
// upkeep"): each opens a popover whose edits write one pass's half alone.
import { beforeEach, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { KnowledgeAutomaticPopover } from "@/components/knowledge/KnowledgeAutomaticPopover";
import { MemoryAutomaticPopover } from "@/components/memory/MemoryAutomaticPopover";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { InternalEngineConfig, UpkeepSetting } from "@/lib/api/internalEngine";
import { acceptance } from "@/test/acceptance";

const MINUTE = 60_000;
const at = (minutes: number) => new Date(Date.now() + minutes * MINUTE).toISOString();

let config: Partial<InternalEngineConfig> = {};
const setUpkeep = vi.fn();
const setOwner = vi.fn();
const curate = vi.fn();
let machines: { machine_id: string; name: string; is_self: boolean }[] = [];

vi.mock("@/lib/hooks/useInternalEngine", () => ({
  useInternalEngineConfig: () => ({ data: config }),
  useCofferModelSet: () => (config.model === undefined ? undefined : Boolean(config.model)),
  useSetUpkeep: () => ({ isPending: false, mutate: setUpkeep }),
  useSetCurationOwner: () => ({ isPending: false, mutate: setOwner }),
}));
vi.mock("@/lib/hooks/useKnowledge", () => ({
  useKnowledgeCollections: () => ({
    data: [
      { uid: "c1", name: "a", pending_count: 2 },
      { uid: "c2", name: "b", pending_count: 0 },
    ],
  }),
  useCurateCollections: () => ({ isPending: false, mutate: curate }),
}));
vi.mock("@/lib/hooks/useMachines", () => ({
  useMachines: () => ({ isPending: false, data: { machines } }),
  useThisMachineId: () => ({ isPending: false, machineId: "m-here" }),
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
  machines = [];
});

acceptance("internal-engine", "the knowledge popover shows and changes curation", () => {
  machines = [
    { machine_id: "m-here", name: "MacBook Pro", is_self: true },
    { machine_id: "m-mini", name: "Mac mini", is_self: false },
  ];
  config = {
    model: "m",
    curate_owner_machine_id: "m-here",
    upkeep: { curate: pass({ last_pass_at: at(-120), next_pass_at: at(58) }) },
  };
  const view = renderIt(<KnowledgeAutomaticPopover />);
  expect(screen.getByTestId("knowledge-automatic")).toHaveTextContent("Automatic · hourly");
  const dialog = open("knowledge-automatic");
  expect(dialog).toHaveTextContent("Automatic curation");
  expect(dialog).toHaveTextContent("Curation runs on");
  expect(dialog).toHaveTextContent("MacBook Pro · this Mac");
  expect(dialog).toHaveTextContent("One Mac curates; the others get the result through sync.");
  expect(dialog).toHaveTextContent(/Last pass 2h ago · next in 58m/);

  fireEvent.click(within(dialog).getByRole("switch", { name: "Automatic curation" }));
  expect(setUpkeep).toHaveBeenLastCalledWith({ pass: "curate", enabled: false });
  pickInterval(dialog, "3 hours");
  expect(setUpkeep).toHaveBeenLastCalledWith({ pass: "curate", interval_s: 10800 });
  fireEvent.click(within(dialog).getByRole("button", { name: "Curate now" }));
  expect(curate).toHaveBeenCalledWith(["c1"]);
  // The default option names its real number.
  fireEvent.keyDown(within(dialog).getByRole("combobox", { name: "Every" }), { key: "ArrowDown" });
  expect(screen.getByRole("option", { name: "Default (1 hour)" })).toBeInTheDocument();
  view.unmount();

  // Without Coffer's model there is nothing to curate with: no control.
  config = { ...config, model: null };
  renderIt(<KnowledgeAutomaticPopover />);
  expect(screen.queryByTestId("knowledge-automatic")).toBeNull();
});

test("one Mac needs no owner choice", () => {
  machines = [{ machine_id: "m-here", name: "MacBook Pro", is_self: true }];
  config = { model: "m", curate_owner_machine_id: null, upkeep: { curate: pass() } };
  renderIt(<KnowledgeAutomaticPopover />);
  const dialog = open("knowledge-automatic");
  expect(dialog).not.toHaveTextContent("Curation runs on");
  expect(dialog).toHaveTextContent("No pass yet");
});

test("another Mac's pass shows where it runs instead of this Mac's timer", () => {
  machines = [
    { machine_id: "m-here", name: "MacBook Pro", is_self: true },
    { machine_id: "m-mini", name: "Mac mini", is_self: false },
  ];
  config = {
    model: "m",
    curate_owner_machine_id: "m-mini",
    upkeep: { curate: pass({ last_pass_at: at(-5), next_pass_at: at(55) }) },
  };
  renderIt(<KnowledgeAutomaticPopover />);
  const dialog = open("knowledge-automatic");
  expect(dialog).toHaveTextContent("Runs on Mac mini");
  expect(dialog).not.toHaveTextContent(/next in/);
});

acceptance("internal-engine", "the curation owner's fault reads in the popover", () => {
  machines = [
    { machine_id: "m-here", name: "MacBook Pro", is_self: true },
    { machine_id: "m-mini", name: "Mac mini", is_self: false },
  ];
  config = { model: "m", curate_owner_machine_id: "m-gone", upkeep: { curate: pass() } };
  renderIt(<KnowledgeAutomaticPopover />);
  expect(screen.getByTestId("knowledge-automatic")).toHaveTextContent("runs on no Mac");
  const dialog = open("knowledge-automatic");
  expect(within(dialog).getByRole("alert")).toHaveTextContent(/curation runs nowhere/);
  expect(dialog).toHaveTextContent("Unknown Mac (m-gone)");
  fireEvent.keyDown(within(dialog).getByRole("combobox", { name: "Curation runs on" }), {
    key: "ArrowDown",
  });
  fireEvent.click(screen.getByRole("option", { name: "MacBook Pro · this Mac" }));
  expect(setOwner).toHaveBeenCalledWith("m-here");
});

acceptance("internal-engine", "the memory popover switches reading and distilling together", () => {
  config = {
    model: null,
    upkeep: {
      aggregate: pass({ last_pass_at: at(-14), next_pass_at: at(46) }),
      distil: pass({ default_interval_s: 21600 }),
    },
  };
  renderIt(<MemoryAutomaticPopover />);
  // Reading needs no model, so the control is there without one.
  expect(screen.getByTestId("memory-automatic")).toHaveTextContent("Automatic · hourly");
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

acceptance("internal-engine", "the popover shows and sets the curation owner", () => {
  machines = [
    { machine_id: "m-here", name: "MacBook Pro", is_self: true },
    { machine_id: "m-mini", name: "Mac mini", is_self: false },
  ];
  config = { model: "m", curate_owner_machine_id: null, upkeep: { curate: pass() } };
  renderIt(<KnowledgeAutomaticPopover />);
  const dialog = open("knowledge-automatic");

  // No owner named: the picker reads "Not chosen" and says every Mac curates.
  expect(dialog).toHaveTextContent("Curation runs on");
  expect(dialog).toHaveTextContent("Not chosen");
  expect(dialog).toHaveTextContent(/every Mac curates/);

  fireEvent.keyDown(within(dialog).getByRole("combobox", { name: "Curation runs on" }), {
    key: "ArrowDown",
  });
  fireEvent.click(screen.getByRole("option", { name: "MacBook Pro · this Mac" }));
  expect(setOwner).toHaveBeenCalledWith("m-here");
});
