// frontend/src/components/channel/ChannelsTable.test.tsx
//
// The channels list (spec channels, FR-041). Each row carries the platform type,
// default agent, a live runtime-health badge (Running/Stopped), the machine the
// channel is bound to, the reach control, a paired-owner cell and a delete
// action — the health, machine and paired cells fed by the per-row
// /channels/{name}/status query, which we stub here. The health badge mirrors
// the MCP-server surface's ServerHealthCell, so this test asserts it reflects
// the adapter `running` state.
//
// The machine cell has four states and each is tested, because they are the
// difference between "quiet because it is someone else's to run" and "quiet
// because it runs nowhere at all" — two facts a single Stopped badge cannot
// tell apart, and only one of which is a fault.
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { PropsWithChildren } from "react";

import { ChannelsTable } from "./ChannelsTable";
import type { ChannelStatus } from "@/lib/api/channels";
import type { ResourceOut } from "@/lib/api/resources";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("@/lib/hooks/useChannels", () => ({
  useChannelStatus: vi.fn(),
  useRebindChannel: vi.fn(),
  CHANNEL_KIND: "channel",
}));
// The bound-agent column shows display names from the provider registry, with
// a static fallback for the keys Coffer knows; stub the registry as loaded.
vi.mock("@/lib/hooks/useAgentProviders", () => ({
  useAgentProviders: vi.fn(() => ({
    data: [{ agent_key: "codex", display_name: "Codex", available: true }],
  })),
}));

// The "Runs on" cell joins the binding against the machine registry and this
// machine's id; both are stubbed so the four states can be set up directly.
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn() }));
vi.mock("@/lib/hooks/useSync", () => ({ useSyncStatus: vi.fn() }));

// The state column is now ScopeControl, so every row reaches the scope /
// agents / enable hooks. `scope` rides the list payload, so useResourceScope
// stays switched off and returns nothing.
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock("@/lib/hooks/useAgents", () => ({
  useAgents: vi.fn(() => ({ data: [{ name: "cc" }] })),
}));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useDeleteResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useChannelStatus, useRebindChannel } = await import("@/lib/hooks/useChannels");
const { useMachines } = await import("@/lib/hooks/useMachines");
const { useSyncStatus } = await import("@/lib/hooks/useSync");
const useChannelStatusMock = vi.mocked(useChannelStatus);

/** This machine, and the other machine in the registry. */
const HERE = "machine-here";
const THERE = "machine-there";

let rebind: { mutate: ReturnType<typeof vi.fn>; isPending: boolean };

/** The registry as the daemon would report it. Pass [] for a vault that has
 *  never converged — the single-machine install, which has no registry and
 *  must still be able to bind. */
function stubMachines(machines: { machine_id: string; name: string; is_self: boolean }[]) {
  vi.mocked(useMachines).mockReturnValue({ data: { machines } } as unknown as ReturnType<
    typeof useMachines
  >);
}

const REGISTRY = [
  { machine_id: HERE, name: "Laptop", is_self: true },
  { machine_id: THERE, name: "Desktop", is_self: false },
];

function status(name: string, over: Partial<ChannelStatus> = {}): ChannelStatus {
  return {
    name,
    channel_type: "telegram",
    enabled: true,
    running: true,
    peer: null,
    callback: null,
    runs_on: HERE,
    runs_here: true,
    ...over,
  };
}

/** Route each row's status query to a fixture keyed by channel name. */
function stubStatuses(byName: Record<string, ChannelStatus | undefined>) {
  useChannelStatusMock.mockImplementation(
    (name: string) => ({ data: byName[name] }) as ReturnType<typeof useChannelStatus>,
  );
}

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children ?? ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function channel(
  name: string,
  agent?: string,
  runsOn: string | null = HERE,
  enabled = true,
): ResourceOut {
  return {
    name,
    kind: "channel",
    config: {
      channel_type: "telegram",
      ...(agent ? { default_agent: agent } : {}),
      ...(runsOn === null ? {} : { runs_on: runsOn }),
    },
    enabled,
  } as unknown as ResourceOut;
}

/** The row's machine picker, by its accessible name. */
function machinePicker(name = "tg") {
  return screen.getByRole("combobox", { name: new RegExp(`machine running ${name}`, "i") });
}

describe("ChannelsTable", () => {
  beforeEach(() => {
    rebind = { mutate: vi.fn(), isPending: false };
    vi.mocked(useRebindChannel).mockReturnValue(
      rebind as unknown as ReturnType<typeof useRebindChannel>,
    );
    vi.mocked(useSyncStatus).mockReturnValue({
      data: { machine_id: HERE },
    } as unknown as ReturnType<typeof useSyncStatus>);
    stubMachines(REGISTRY);
  });
  afterEach(() => vi.clearAllMocks());

  test("renders one row per channel, naming the default agent for a human", () => {
    stubStatuses({ tg: status("tg"), st: status("st"), cx: status("cx") });
    render(
      <ChannelsTable
        items={[channel("tg", "claude_code"), channel("cx", "codex"), channel("st")]}
      />,
      { wrapper: wrap(null) },
    );
    expect(screen.getByText("tg")).toBeInTheDocument();
    expect(screen.getByText("st")).toBeInTheDocument();
    // Display names, never the provider key — from the registry when it has
    // the key, from the static map otherwise.
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("Codex")).toBeInTheDocument();
    expect(screen.queryByText("claude_code")).not.toBeInTheDocument();
    // A config that names no agent shows the empty value, not a made-up key.
    const st = within(screen.getByText("st").closest("tr") as HTMLElement);
    expect(st.queryByText("builtin")).not.toBeInTheDocument();
    expect(st.getAllByText("—").length).toBeGreaterThan(0);
  });

  test("shows a live health badge reflecting the adapter running state", () => {
    // tg's adapter is live -> Running (ok); st's is down -> Stopped (warn).
    stubStatuses({
      tg: status("tg", { running: true }),
      st: status("st", { running: false }),
    });
    render(<ChannelsTable items={[channel("tg"), channel("st")]} />, { wrapper: wrap(null) });

    const badges = screen.getAllByTestId("channel-health-badge");
    expect(badges).toHaveLength(2);
    expect(screen.getByText("Running")).toHaveClass("text-status-ok");
    // Stopped is attention, not "unknown": the same warn tone the detail
    // page's Status card uses.
    expect(screen.getByText("Stopped")).toHaveClass("text-status-warn");
  });

  test("the toolbar offers the shared three-state reach filter", () => {
    stubStatuses({ tg: status("tg"), st: status("st") });
    render(<ChannelsTable items={[channel("tg"), channel("st", undefined, HERE, false)]} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByRole("columnheader", { name: "Reach" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("combobox", { name: "Reach" }));
    fireEvent.click(screen.getByRole("option", { name: "Disabled" }));
    expect(screen.getByText("st")).toBeInTheDocument();
    expect(screen.queryByText("tg")).not.toBeInTheDocument();
  });

  test("shows the paired owner when the channel has a peer", () => {
    stubStatuses({
      tg: status("tg", {
        running: true,
        peer: {
          chat_id: "123",
          display_name: "Alice",
          paired_at: "2026-07-09T00:00:00Z",
          active_conversation_id: null,
        },
      }),
    });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
  });

  test("the reach column keeps the shared header, not a kind-local 'State'", () => {
    // Every other kind's table calls this column Reach; this one was the last
    // straggler, and two names for one control is how the column drifts into
    // meaning two different things.
    stubStatuses({ tg: status("tg") });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    expect(screen.getByRole("columnheader", { name: /^reach$/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^state$/i })).toBeNull();
    // And it is a DIFFERENT question from the machine binding beside it.
    expect(screen.getByRole("columnheader", { name: /^runs on$/i })).toBeInTheDocument();
  });

  test("the state column is the reach control, not a static badge", () => {
    stubStatuses({ tg: status("tg") });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    const row = within(screen.getByText("tg").closest("tr") as HTMLElement);
    // ONE button, whose label states the channel's current reach.
    const reach = within(row.getByTestId("scope-control")).getByRole("button");
    expect(reach).toHaveTextContent(/^every agent$/i);
    // And unlike a badge it is the place reach is changed: it opens the panel
    // carrying the three states as choices.
    fireEvent.click(reach);
    expect(screen.getByRole("radio", { name: /^disabled$/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /every agent/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /only selected agents/i })).toBeInTheDocument();
  });

  test("every row offers a labelled delete, behind a confirmation", () => {
    stubStatuses({ tg: status("tg") });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    const row = within(screen.getByText("tg").closest("tr") as HTMLElement);
    // Labelled, not a bare icon — the same affordance the other tables show.
    const del = row.getByRole("button", { name: /delete channel: tg/i });
    expect(del).toHaveTextContent(/delete/i);

    fireEvent.click(del);
    expect(screen.getByRole("dialog")).toHaveTextContent(/delete channel/i);
  });

  test("selecting rows reveals the shared reach control and a bulk delete", () => {
    stubStatuses({ tg: status("tg"), st: status("st") });
    render(<ChannelsTable items={[channel("tg"), channel("st")]} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    // The same one-button control the rows carry, naming the action because a
    // mixed selection has no single reach to report.
    const bar = within(screen.getByTestId("bulk-reach-control"));
    expect(bar.getByRole("button")).toHaveTextContent(/set reach/i);
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  test("marks the bound machine when it is this one", () => {
    stubStatuses({ tg: status("tg", { runs_on: HERE, runs_here: true }) });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    // The registry's name, marked as this machine — "Stopped" beside it would
    // be a fault to chase, which is exactly what the marking is for.
    expect(machinePicker()).toHaveTextContent(/Laptop · this machine/i);
  });

  test("names the other machine when the channel is bound there", () => {
    stubStatuses({ tg: status("tg", { running: false, runs_on: THERE, runs_here: false }) });
    render(<ChannelsTable items={[channel("tg", "builtin", THERE)]} />, { wrapper: wrap(null) });

    expect(machinePicker()).toHaveTextContent(/^Desktop$/);
    // Not this machine's to run, so a stopped adapter here is not a fault.
    expect(screen.getByText("Stopped")).toBeInTheDocument();
  });

  test("a binding nobody claims reads as a fault, never as a blank", () => {
    // Retiring a machine leaves its channels naming it. The channel runs on no
    // machine at all until it is rebound, so the cell must say so rather than
    // quietly showing an empty box or the first machine in the list.
    stubStatuses({
      tg: status("tg", { running: false, runs_on: "machine-gone", runs_here: false }),
    });
    render(<ChannelsTable items={[channel("tg", "builtin", "machine-gone")]} />, {
      wrapper: wrap(null),
    });

    const picker = machinePicker();
    expect(picker).toHaveTextContent(/unknown machine \(machine-gone\)/i);
    expect(picker.className).toContain("text-destructive");
  });

  test("an unbound channel says so, and the state is not offered as a choice", () => {
    stubStatuses({ tg: status("tg", { running: false, runs_on: null, runs_here: false }) });
    render(<ChannelsTable items={[channel("tg", "builtin", null)]} />, { wrapper: wrap(null) });

    const picker = machinePicker();
    expect(picker).toHaveTextContent(/not bound/i);
    // Warn, not error: nothing is broken, nothing has been chosen yet.
    expect(picker.className).toContain("status-warn");

    // jsdom has no PointerEvent, so open the Radix listbox from the keyboard.
    fireEvent.keyDown(picker, { key: "ArrowDown" });
    const options = screen.getAllByRole("option").map((o) => o.textContent ?? "");
    expect(options).toEqual(["Laptop · this machine", "Desktop"]);
    // "Not bound" is reportable, never choosable — binding to nobody is asking
    // for a channel that runs nowhere.
    expect(options.some((o) => /not bound/i.test(o))).toBe(false);
  });

  test("this machine is offered even when the registry is empty", () => {
    // A single-machine install has never converged and so has no registry at
    // all; an empty pick-list would leave it unable to bind anything.
    stubMachines([]);
    stubStatuses({ tg: status("tg", { runs_on: null, runs_here: false }) });
    render(<ChannelsTable items={[channel("tg", "builtin", null)]} />, { wrapper: wrap(null) });

    fireEvent.keyDown(machinePicker(), { key: "ArrowDown" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "This machine · this machine",
    ]);
  });

  test("picking a machine rebinds through the channel's own config", () => {
    stubStatuses({ tg: status("tg", { runs_on: HERE, runs_here: true }) });
    render(<ChannelsTable items={[channel("tg", "builtin")]} />, { wrapper: wrap(null) });

    fireEvent.keyDown(machinePicker(), { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "Desktop" }));

    // The whole config rides along: a rebind that dropped the credential refs
    // would move the channel and break it in the same request.
    expect(rebind.mutate).toHaveBeenCalledWith({
      config: { channel_type: "telegram", default_agent: "builtin", runs_on: HERE },
      runsOn: THERE,
      machine: "Desktop",
    });
  });

  test("interacting with the machine picker does not navigate away", () => {
    stubStatuses({ tg: status("tg") });
    render(<ChannelsTable items={[channel("tg")]} />, { wrapper: wrap(null) });

    // The row navigates …
    fireEvent.click(screen.getByText("tg"));
    expect(navigateMock).toHaveBeenCalledWith("/channels/tg");

    // … but the control inside it does not: opening a picker is not a request
    // to leave the page, and losing the row mid-gesture would be maddening.
    navigateMock.mockClear();
    fireEvent.click(machinePicker());
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("falls back to a placeholder health cell before the status loads", () => {
    stubStatuses({ tg: undefined });
    const { container } = render(<ChannelsTable items={[channel("tg")]} />, {
      wrapper: wrap(null),
    });
    expect(screen.queryByTestId("channel-health-badge")).not.toBeInTheDocument();
    // The em-dash placeholder stands in until the query resolves.
    expect(within(container).getByText("tg")).toBeInTheDocument();
  });
});
