// frontend/src/components/channel/ChannelsTable.test.tsx
//
// The channels list (spec channels "List every Coffer-hosted channel on one
// management surface"). Each row carries the platform type,
// default agent, a live runtime-health badge (Running/Stopped), the machine the
// channel is bound to, the reach control, a paired-owner cell and a delete
// action — the health, machine and paired cells fed by the per-row
// /channels/{uid}/status query, which we stub here. The health badge mirrors
// the MCP-server surface's ServerHealthCell, so this test asserts it reflects
// the adapter `running` state.
//
// The machine cell has four states and each is tested, because they are the
// difference between "quiet because it is someone else's to run" and "quiet
// because it runs nowhere at all" — two facts a single Stopped badge cannot
// tell apart, and only one of which is a fault.
//
// Two identities run through every fixture and never coincide: the uid the row
// is addressed by (its status query, its link, its reach and delete calls) and
// the name it is read by. The same split applies to the bound agent — the
// config holds an agent's uid, the column prints that agent's name.
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
// The "Runs on" cell joins the binding against the machine registry and this
// machine's id; both are stubbed so the four states can be set up directly.
vi.mock("@/lib/hooks/useMachines", () => ({ useMachines: vi.fn(), useThisMachineId: vi.fn() }));

// The state column is now ScopeControl, so every row reaches the scope /
// agents / enable hooks. `scope` rides the list payload, so useResourceScope
// stays switched off and returns nothing.
vi.mock("@/lib/hooks/useScope", () => ({
  useResourceScope: vi.fn(() => ({ data: undefined })),
  useUpdateResourceScope: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
// The bound-agent column resolves a row's `default_agent` uid against the
// registered AGENT RESOURCES — the same list the reach control's agent picker
// reads. It used to resolve a provider KEY against the chat provider registry,
// which was a second vocabulary for the same thing.
vi.mock("@/lib/hooks/useAgents", () => ({ useAgents: vi.fn() }));
vi.mock("@/lib/hooks/useResourceMutations", () => ({
  useDeleteResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useEnableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisableResource: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

const { useChannelStatus, useRebindChannel } = await import("@/lib/hooks/useChannels");
const { useMachines, useThisMachineId } = await import("@/lib/hooks/useMachines");
const { useAgents } = await import("@/lib/hooks/useAgents");
const useChannelStatusMock = vi.mocked(useChannelStatus);

/** The channels these rows are about. A uid to address, a name to read — and
 *  nothing derives one from the other, so an assertion about the link cannot
 *  be satisfied by the label or the other way round. */
const TG = { uid: "u-3d9a1f77", name: "tg" };
const ST = { uid: "u-c0be4512", name: "st" };
const CX = { uid: "u-9ab27e40", name: "cx" };

/** The agents a binding can point at, as `useAgents` reports them. */
const CLAUDE = { uid: "u-6c1d0b83", name: "claude-code" };
const CODEX = { uid: "u-f04a927e", name: "codex" };

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

function status(
  ch: { uid: string; name: string },
  over: Partial<ChannelStatus> = {},
): ChannelStatus {
  return {
    ...ch,
    channel_type: "telegram",
    enabled: true,
    running: true,
    pending_pairing: false,
    peer: null,
    inbound: null,
    runs_on: HERE,
    runs_here: true,
    ...over,
  };
}

/** Route each row's status query to a fixture keyed by channel UID — which is
 *  what the cells pass, because that is what the route takes. */
function stubStatuses(byUid: Record<string, ChannelStatus | undefined>) {
  useChannelStatusMock.mockImplementation(
    (uid: string) => ({ data: byUid[uid] }) as ReturnType<typeof useChannelStatus>,
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
  ch: { uid: string; name: string },
  agent?: string,
  runsOn: string | null = HERE,
  enabled = true,
): ResourceOut {
  return {
    ...ch,
    kind: "channel",
    config: {
      channel_type: "telegram",
      ...(agent ? { default_agent: agent } : {}),
      ...(runsOn === null ? {} : { runs_on: runsOn }),
    },
    enabled,
  } as unknown as ResourceOut;
}

/** The row's machine picker, by its accessible name — which spells the
 *  channel's NAME, because that is the only half of its identity a person can
 *  read out. */
function machinePicker(name = TG.name) {
  return screen.getByRole("combobox", { name: new RegExp(`machine running ${name}`, "i") });
}

describe("ChannelsTable", () => {
  beforeEach(() => {
    rebind = { mutate: vi.fn(), isPending: false };
    vi.mocked(useRebindChannel).mockReturnValue(
      rebind as unknown as ReturnType<typeof useRebindChannel>,
    );
    vi.mocked(useThisMachineId).mockReturnValue({ machineId: HERE, isPending: false });
    stubMachines(REGISTRY);
    vi.mocked(useAgents).mockReturnValue({
      data: [CLAUDE, CODEX],
    } as unknown as ReturnType<typeof useAgents>);
  });
  afterEach(() => vi.clearAllMocks());

  test("renders one row per channel, naming the default agent for a human", () => {
    stubStatuses({ [TG.uid]: status(TG), [ST.uid]: status(ST), [CX.uid]: status(CX) });
    render(
      <ChannelsTable items={[channel(TG, CLAUDE.uid), channel(CX, CODEX.uid), channel(ST)]} />,
      { wrapper: wrap(null) },
    );
    expect(screen.getByText(TG.name)).toBeInTheDocument();
    expect(screen.getByText(ST.name)).toBeInTheDocument();
    // The agents' NAMES, resolved from their uids. The uid is stored, never
    // shown: it is the one part of an agent's identity nobody can read.
    expect(screen.getByText(CLAUDE.name)).toBeInTheDocument();
    expect(screen.getByText(CODEX.name)).toBeInTheDocument();
    expect(screen.queryByText(CLAUDE.uid)).not.toBeInTheDocument();
    // A config that names no agent shows the empty value, not a made-up key.
    const st = within(screen.getByText(ST.name).closest("tr") as HTMLElement);
    expect(st.getAllByText("—").length).toBeGreaterThan(0);
  });

  test("a bound agent this vault cannot resolve is shown as the uid it is", () => {
    // The binding really does point somewhere. An empty cell would hide a
    // channel bound to an agent that is gone; the raw uid is what lets the
    // owner see what it says and re-bind it.
    stubStatuses({ [TG.uid]: status(TG) });
    render(<ChannelsTable items={[channel(TG, "u-deadbeef")]} />, { wrapper: wrap(null) });

    expect(screen.getByText("u-deadbeef")).toBeInTheDocument();
  });

  test("shows a live health badge reflecting the adapter running state", () => {
    // tg's adapter is live -> Running (ok); st's is down -> Stopped (warn).
    stubStatuses({
      [TG.uid]: status(TG, { running: true }),
      [ST.uid]: status(ST, { running: false }),
    });
    render(<ChannelsTable items={[channel(TG), channel(ST)]} />, { wrapper: wrap(null) });

    const badges = screen.getAllByTestId("channel-health-badge");
    expect(badges).toHaveLength(2);
    expect(screen.getByText("Running")).toHaveClass("text-status-ok");
    // Stopped is attention, not "unknown": the same warn tone the detail
    // page's Status card uses.
    expect(screen.getByText("Stopped")).toHaveClass("text-status-warn");
  });

  test("the toolbar offers the shared three-state reach filter", () => {
    stubStatuses({ [TG.uid]: status(TG), [ST.uid]: status(ST) });
    render(<ChannelsTable items={[channel(TG), channel(ST, undefined, HERE, false)]} />, {
      wrapper: wrap(null),
    });
    expect(screen.getByRole("columnheader", { name: "Reach" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("combobox", { name: "Reach" }));
    fireEvent.click(screen.getByRole("option", { name: "Disabled" }));
    expect(screen.getByText(ST.name)).toBeInTheDocument();
    expect(screen.queryByText(TG.name)).not.toBeInTheDocument();
  });

  test("shows the paired owner when the channel has a peer", () => {
    stubStatuses({
      [TG.uid]: status(TG, {
        running: true,
        peer: {
          chat_id: "123",
          display_name: "Alice",
          paired_at: "2026-07-09T00:00:00Z",
          active_conversation_id: null,
        },
      }),
    });
    render(<ChannelsTable items={[channel(TG)]} />, { wrapper: wrap(null) });
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
  });

  test("the reach column keeps the shared header, not a kind-local 'State'", () => {
    // Every other kind's table calls this column Reach; this one was the last
    // straggler, and two names for one control is how the column drifts into
    // meaning two different things.
    stubStatuses({ [TG.uid]: status(TG) });
    render(<ChannelsTable items={[channel(TG)]} />, { wrapper: wrap(null) });

    expect(screen.getByRole("columnheader", { name: /^reach$/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /^state$/i })).toBeNull();
    // And it is a DIFFERENT question from the machine binding beside it.
    expect(screen.getByRole("columnheader", { name: /^runs on$/i })).toBeInTheDocument();
  });

  test("the state column is the reach control, not a static badge", () => {
    stubStatuses({ [TG.uid]: status(TG) });
    render(<ChannelsTable items={[channel(TG)]} />, { wrapper: wrap(null) });

    const row = within(screen.getByText(TG.name).closest("tr") as HTMLElement);
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
    stubStatuses({ [TG.uid]: status(TG) });
    render(<ChannelsTable items={[channel(TG)]} />, { wrapper: wrap(null) });

    const row = within(screen.getByText(TG.name).closest("tr") as HTMLElement);
    // Labelled, not a bare icon — the same affordance the other tables show.
    const del = row.getByRole("button", { name: new RegExp(`delete channel: ${TG.name}`, "i") });
    expect(del).toHaveTextContent(/delete/i);

    fireEvent.click(del);
    expect(screen.getByRole("dialog")).toHaveTextContent(/delete channel/i);
  });

  test("selecting rows reveals the shared reach control and a bulk delete", () => {
    stubStatuses({ [TG.uid]: status(TG), [ST.uid]: status(ST) });
    render(<ChannelsTable items={[channel(TG), channel(ST)]} />, { wrapper: wrap(null) });
    expect(screen.queryByTestId("bulk-reach-control")).toBeNull();

    fireEvent.click(screen.getAllByRole("checkbox")[0]);
    // The same one-button control the rows carry, naming the action because a
    // mixed selection has no single reach to report.
    const bar = within(screen.getByTestId("bulk-reach-control"));
    expect(bar.getByRole("button")).toHaveTextContent(/set reach/i);
    expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument();
  });

  test("marks the bound machine when it is this one", () => {
    stubStatuses({ [TG.uid]: status(TG, { runs_on: HERE, runs_here: true }) });
    render(<ChannelsTable items={[channel(TG)]} />, { wrapper: wrap(null) });

    // The registry's name, marked as this machine — "Stopped" beside it would
    // be a fault to chase, which is exactly what the marking is for.
    expect(machinePicker()).toHaveTextContent(/Laptop · this machine/i);
  });

  test("names the other machine when the channel is bound there", () => {
    stubStatuses({ [TG.uid]: status(TG, { running: false, runs_on: THERE, runs_here: false }) });
    render(<ChannelsTable items={[channel(TG, CLAUDE.uid, THERE)]} />, { wrapper: wrap(null) });

    expect(machinePicker()).toHaveTextContent(/^Desktop$/);
    // Not this machine's to run, so a stopped adapter here is not a fault.
    expect(screen.getByText("Stopped")).toBeInTheDocument();
  });

  test("a binding nobody claims reads as a fault, never as a blank", () => {
    // Retiring a machine leaves its channels naming it. The channel runs on no
    // machine at all until it is rebound, so the cell must say so rather than
    // quietly showing an empty box or the first machine in the list.
    stubStatuses({
      [TG.uid]: status(TG, { running: false, runs_on: "machine-gone", runs_here: false }),
    });
    render(<ChannelsTable items={[channel(TG, CLAUDE.uid, "machine-gone")]} />, {
      wrapper: wrap(null),
    });

    const picker = machinePicker();
    expect(picker).toHaveTextContent(/unknown machine \(machine-gone\)/i);
    expect(picker.className).toContain("text-destructive");
  });

  test("an unbound channel says so, and the state is not offered as a choice", () => {
    stubStatuses({ [TG.uid]: status(TG, { running: false, runs_on: null, runs_here: false }) });
    render(<ChannelsTable items={[channel(TG, CLAUDE.uid, null)]} />, { wrapper: wrap(null) });

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
    stubStatuses({ [TG.uid]: status(TG, { runs_on: null, runs_here: false }) });
    render(<ChannelsTable items={[channel(TG, CLAUDE.uid, null)]} />, { wrapper: wrap(null) });

    fireEvent.keyDown(machinePicker(), { key: "ArrowDown" });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "This machine · this machine",
    ]);
  });

  test("picking a machine rebinds through the channel's own config", () => {
    stubStatuses({ [TG.uid]: status(TG, { runs_on: HERE, runs_here: true }) });
    render(<ChannelsTable items={[channel(TG, CLAUDE.uid)]} />, { wrapper: wrap(null) });

    fireEvent.keyDown(machinePicker(), { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("option", { name: "Desktop" }));

    // The whole config rides along: a rebind that dropped the credential refs
    // would move the channel and break it in the same request.
    expect(rebind.mutate).toHaveBeenCalledWith({
      config: { channel_type: "telegram", default_agent: CLAUDE.uid, runs_on: HERE },
      runsOn: THERE,
      machine: "Desktop",
    });
  });

  test("interacting with the machine picker does not navigate away", () => {
    stubStatuses({ [TG.uid]: status(TG) });
    render(<ChannelsTable items={[channel(TG)]} />, { wrapper: wrap(null) });

    // The row navigates — to the uid, which is what the detail route takes …
    fireEvent.click(screen.getByText(TG.name));
    expect(navigateMock).toHaveBeenCalledWith(`/channels/${TG.uid}`);

    // … but the control inside it does not: opening a picker is not a request
    // to leave the page, and losing the row mid-gesture would be maddening.
    navigateMock.mockClear();
    fireEvent.click(machinePicker());
    expect(navigateMock).not.toHaveBeenCalled();
  });

  test("falls back to a placeholder health cell before the status loads", () => {
    stubStatuses({ [TG.uid]: undefined });
    const { container } = render(<ChannelsTable items={[channel(TG)]} />, {
      wrapper: wrap(null),
    });
    expect(screen.queryByTestId("channel-health-badge")).not.toBeInTheDocument();
    // The em-dash placeholder stands in until the query resolves.
    expect(within(container).getByText(TG.name)).toBeInTheDocument();
  });
});
