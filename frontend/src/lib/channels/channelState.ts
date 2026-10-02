// frontend/src/lib/channels/channelState.ts
// One answer to "what state is this channel in?", shared by the list row, the
// detail header and the status banner so the three can never disagree.
//
// The inputs are the resource (enabled, its configured machine), the live
// status (`GET /channels/{uid}/status`, which may still be loading or may have
// failed) and the machine registry. The answer names a state, the list group
// it belongs to, the tone of its status word and the header's one primary
// action. Order matters: where the channel runs comes first (a channel another
// machine runs is quiet here by design, whatever its local adapter says), then
// whether it is switched on, then the connection, then pairing.
import type { StatusTone } from "@/lib/statusTone";
import type { ChannelStatus } from "@/lib/api/channels";
import { bindingState } from "@/lib/channels/channelBinding";

export type ChannelStateKey =
  | "loading"
  | "unavailable"
  | "unbound"
  | "unknownMachine"
  | "elsewhere"
  | "off"
  | "connecting"
  | "reconnecting"
  | "kicked"
  | "sdkMissing"
  | "connectFailed"
  | "stopped"
  | "notPaired"
  | "connected";

/** The list's groups, in the order the list shows them. */
export const CHANNEL_GROUPS = ["attention", "connected", "elsewhere", "off"] as const;
type ChannelGroup = (typeof CHANNEL_GROUPS)[number];

/** The header's one primary action for a state. */
export type ChannelPrimaryAction =
  | "sendTest"
  | "reconnect"
  | "takeBack"
  | "retryStart"
  | "refresh"
  | "replaceSecret"
  | "runHere"
  | "runHereConfirm"
  | "turnOn"
  | null;

export interface ChannelView {
  state: ChannelStateKey;
  group: ChannelGroup;
  tone: StatusTone;
  primary: ChannelPrimaryAction;
  /** The machine the channel is bound to (null when unbound). */
  runsOn: string | null;
  /** Whether this machine runs it. */
  runsHere: boolean;
}

export interface ChannelStateInput {
  enabled: boolean;
  config: Record<string, unknown>;
  status: ChannelStatus | undefined;
  /** The status read failed (the adapter or the daemon did not answer). */
  statusFailed: boolean;
  selfId: string | null;
  knownMachines: readonly string[];
}

const TONE: Record<ChannelStateKey, StatusTone> = {
  loading: "off",
  unavailable: "warn",
  unbound: "err",
  unknownMachine: "err",
  elsewhere: "off",
  off: "off",
  connecting: "warn",
  reconnecting: "warn",
  kicked: "err",
  sdkMissing: "err",
  connectFailed: "err",
  stopped: "err",
  notPaired: "warn",
  connected: "ok",
};

const PRIMARY: Record<ChannelStateKey, ChannelPrimaryAction> = {
  loading: null,
  unavailable: "refresh",
  unbound: "runHere",
  unknownMachine: "runHere",
  elsewhere: "runHereConfirm",
  off: "turnOn",
  connecting: null,
  reconnecting: "reconnect",
  kicked: "takeBack",
  sdkMissing: "retryStart",
  connectFailed: "replaceSecret",
  stopped: "replaceSecret",
  notPaired: null,
  connected: "sendTest",
};

function configuredMachine(config: Record<string, unknown>): string | null {
  const v = config.runs_on;
  return typeof v === "string" && v !== "" ? v : null;
}

function localState(status: ChannelStatus): ChannelStateKey {
  const ws = status.inbound?.websocket_state ?? null;
  if (ws === "kicked") return "kicked";
  if (ws === "sdk_missing") return "sdkMissing";
  if (ws === "error") return "connectFailed";
  if (!status.running) return "stopped";
  if (status.inbound && ws !== "connected") {
    // A first connection and a lost one look the same on the wire; the error
    // left behind by the last attempt is what tells them apart.
    return status.inbound.websocket_error ? "reconnecting" : "connecting";
  }
  return status.peer === null ? "notPaired" : "connected";
}

function stateOf(input: ChannelStateInput, runsOn: string | null): ChannelStateKey {
  const { status } = input;
  if (input.statusFailed && status === undefined) return "unavailable";
  const binding = bindingState(runsOn, {
    selfId: input.selfId,
    known: input.knownMachines,
    runsHere: status?.runs_here,
  });
  if (binding === "unbound") return "unbound";
  if (binding === "unknown") return "unknownMachine";
  if (binding === "other") return "elsewhere";
  if (!input.enabled) return "off";
  if (status === undefined) return "loading";
  return localState(status);
}

function groupOf(state: ChannelStateKey, status: ChannelStatus | undefined): ChannelGroup {
  if (state === "elsewhere") return "elsewhere";
  if (state === "off") return "off";
  if (state === "loading" || state === "connecting") return "connected";
  if (state === "connected") {
    return (status?.diagnostics ?? []).length > 0 ? "attention" : "connected";
  }
  return "attention";
}

/** Describe one channel: its state, list group, status tone and primary action. */
export function describeChannel(input: ChannelStateInput): ChannelView {
  // The daemon's answer wins once there is one; the config is the fallback.
  const runsOn = input.status ? input.status.runs_on : configuredMachine(input.config);
  const state = stateOf(input, runsOn);
  return {
    state,
    group: groupOf(state, input.status),
    tone: TONE[state],
    primary: PRIMARY[state],
    runsOn,
    runsHere: input.status?.runs_here ?? (runsOn !== null && runsOn === input.selfId),
  };
}

/** The channel's platform key (`seatalk` / `telegram`) from its config. */
export function channelPlatform(config: Record<string, unknown>): string {
  return typeof config.channel_type === "string" ? config.channel_type : "telegram";
}
