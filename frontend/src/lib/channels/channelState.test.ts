// frontend/src/lib/channels/channelState.test.ts
// The one answer to "what state is this channel in?" — where it runs first,
// then whether it is on, then its connection, then pairing — and the list
// group and fix action each state brings.
import { describe, expect, test } from "vitest";

import type { ChannelStatus } from "@/lib/api/channels";
import { describeChannel, type ChannelStateInput } from "@/lib/channels/channelState";
import { HERE, THERE, makeChannel, makeStatus } from "@/test/channelKit";

const seatalk = makeChannel();

function input(
  status: Partial<ChannelStatus> | undefined,
  over: Partial<ChannelStateInput> = {},
): ChannelStateInput {
  return {
    enabled: true,
    config: seatalk.config,
    status: status === undefined ? undefined : makeStatus(seatalk, status),
    statusFailed: false,
    selfId: HERE,
    knownMachines: [HERE, THERE],
    ...over,
  };
}

const ws = (websocket_state: string, websocket_error: string | null = null) =>
  ({ inbound: { websocket_state, websocket_error } }) as Partial<ChannelStatus>;

describe("describeChannel", () => {
  test.each([
    ["connected", {}, "connected", "connected", "ok", null],
    ["connecting", ws("connecting"), "connecting", "connected", "warn", null],
    [
      "reconnecting",
      ws("connecting", "closed 1006"),
      "reconnecting",
      "attention",
      "warn",
      "reconnect",
    ],
    ["kicked", ws("kicked"), "kicked", "attention", "err", "takeBack"],
    ["sdk missing", ws("sdk_missing"), "sdkMissing", "attention", "err", "retryStart"],
    // spec channels/seatalk "Report the websocket connection as the channel's inbound state":
    // only SeaTalk refusing the app is a rejected secret; a network failure is not.
    [
      "rejected",
      ws("rejected", "RegisterError: code=1"),
      "connectFailed",
      "attention",
      "err",
      "replaceSecret",
    ],
    [
      "network error",
      ws("error", "gaierror: nodename nor servname provided"),
      "unreachable",
      "attention",
      "warn",
      "reconnect",
    ],
    ["stopped", { running: false, inbound: null }, "stopped", "attention", "err", "replaceSecret"],
    [
      "secret waiting for approval",
      {
        running: false,
        inbound: null,
        secret_approval: { state: "pending", secret_ref: "channel/x/secret" },
      },
      "waitingApproval",
      "attention",
      "warn",
      "openSecrets",
    ],
    [
      "secret refused",
      {
        running: false,
        inbound: null,
        secret_approval: { state: "refused", secret_ref: "channel/x/secret" },
      },
      "approvalRefused",
      "attention",
      "err",
      "openSecrets",
    ],
    ["not paired", { people: [] }, "notPaired", "attention", "warn", null],
  ])("%s", (_label, status, state, group, tone, primary) => {
    expect(describeChannel(input(status as Partial<ChannelStatus>))).toMatchObject({
      state,
      group,
      tone,
      primary,
    });
  });

  test("another machine's channel is quiet here by design, whatever its local adapter says", () => {
    const view = describeChannel(
      input({ running: false, runs_on: THERE, runs_here: false }, { config: { runs_on: THERE } }),
    );
    expect(view).toMatchObject({ state: "elsewhere", group: "elsewhere", tone: "off" });
    expect(view.primary).toBe("runHereConfirm");
  });

  test("a machine nobody claims, or none at all, runs nowhere", () => {
    expect(describeChannel(input({ runs_on: "ghost", runs_here: false })).state).toBe(
      "unknownMachine",
    );
    expect(describeChannel(input({ runs_on: null, runs_here: false })).state).toBe("unbound");
  });

  // spec channels "Report a channel that is starting apart from one that failed to start"
  test("a channel switched on but not yet started is connecting, never a rejected secret", () => {
    const view = describeChannel(input({ running: false, starting: true, inbound: null }));
    expect(view).toMatchObject({ state: "connecting", tone: "warn", primary: null });
    expect(view.group).not.toBe("attention");
  });

  test("a status read before the switch is not this run's failure", () => {
    // The resource already says on; the status cached from while it was off
    // still says off and not running.
    const stale = describeChannel(input({ enabled: false, running: false, inbound: null }));
    expect(stale.state).toBe("connecting");
  });

  test("a channel switched off reads Off, in its own group", () => {
    expect(describeChannel(input({ running: false }, { enabled: false }))).toMatchObject({
      state: "off",
      group: "off",
      primary: "turnOn",
    });
  });

  test("a status that failed to load is Unknown and asks for a retry", () => {
    expect(describeChannel(input(undefined, { statusFailed: true }))).toMatchObject({
      state: "unavailable",
      group: "attention",
      primary: "refresh",
    });
    // Still loading is not a fault.
    expect(describeChannel(input(undefined)).group).toBe("connected");
  });

  test("a connected channel with a diagnostic moves to Needs attention", () => {
    const view = describeChannel(input({ diagnostics: [{ code: "privacy", message: "x" }] }));
    expect(view).toMatchObject({ state: "connected", group: "attention" });
  });

  test("telegram has no inbound connection: running and paired is connected", () => {
    const tg = makeChannel({ config: { channel_type: "telegram" } });
    const view = describeChannel({
      ...input(undefined),
      config: tg.config,
      status: makeStatus(tg),
    });
    expect(view.state).toBe("connected");
  });
});
