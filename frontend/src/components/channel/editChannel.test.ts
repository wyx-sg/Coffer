// frontend/src/components/channel/editChannel.test.ts
//
// The edit-channel planning contract (counterpart to AddChannelDialog's
// register flow): rotating a secret writes the NEW value to the SAME
// credential ref the channel already points at (so the config never changes
// when only a secret rotates), and the config PATCH preserves every existing
// `*_ref` while only the mutable fields (bound agent, SeaTalk app id) change.
// A blank secret field means "leave it as-is" — no credential write at all.
//
// Every input below carries BOTH of the channel's strings, because they are no
// longer one: the `uid` the PATCH is addressed to, and the `name` that mints a
// credential ref and reads out in the toast. They are spelled differently on
// purpose — a fixture whose uid reads as its name would let an assertion about
// the address pass on the label.
//
// `default_agent` is an agent RESOURCE UID for the same reason (it used to be
// the chat provider key `claude_code`), so the values below are opaque too.
import { describe, expect, test } from "vitest";

import { planChannelEdit } from "./editChannel";

/** The two channels every case below edits: a uid to address, a name to read. */
const TG = { uid: "u-3d9a1f77", name: "tg" };
const ST = { uid: "u-c0be4512", name: "st" };

/** Agents the bindings point at — uids, never the names they display under. */
const AGENT_A = "u-a17c4e90";
const AGENT_B = "u-b52f08d3";

describe("planChannelEdit", () => {
  test("the plan carries the uid to address and the name to read out", () => {
    // Both, and separately. The apply PATCHes `/resources/{uid}` and toasts the
    // name, so a plan that carried one of them would either address the wrong
    // row or tell the user about a channel by an id they cannot read.
    const plan = planChannelEdit({
      ...TG,
      config: { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" },
      values: { default_agent: AGENT_A },
    });

    expect(plan.uid).toBe(TG.uid);
    expect(plan.name).toBe(TG.name);
  });

  test("telegram: rotating the token writes the same ref, agent change patches config", () => {
    const plan = planChannelEdit({
      ...TG,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_B, bot_token: "999:newtoken" },
    });

    expect(plan.secrets).toEqual([{ ref: "channel/tg/bot-token", value: "999:newtoken" }]);
    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      default_agent: AGENT_B,
    });
  });

  test("telegram: a blank token rotates nothing but still patches the agent", () => {
    const plan = planChannelEdit({
      ...TG,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_B, bot_token: "" },
    });

    expect(plan.secrets).toEqual([]);
    expect(plan.config.default_agent).toBe(AGENT_B);
  });

  test("telegram: preserves an unknown config field (default_agent_config)", () => {
    const plan = planChannelEdit({
      ...TG,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: AGENT_A,
        default_agent_config: { temperature: 0.2 },
      },
      values: { default_agent: AGENT_A, bot_token: "" },
    });

    expect(plan.config.default_agent_config).toEqual({ temperature: 0.2 });
  });

  test("seatalk: rotates both secrets to their existing refs and updates app id", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-old",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: AGENT_A,
      },
      values: {
        default_agent: AGENT_A,
        app_id: "app-new",
        app_secret: "s1",
        signing_secret: "s2",
      },
    });

    expect(plan.secrets).toEqual([
      { ref: "channel/st/app-secret", value: "s1" },
      { ref: "channel/st/signing-secret", value: "s2" },
    ]);
    expect(plan.config).toEqual({
      channel_type: "seatalk",
      // Absent in the stored config means webhook; the PATCH says so out loud.
      delivery: "webhook",
      app_id: "app-new",
      app_secret_ref: "channel/st/app-secret",
      signing_secret_ref: "channel/st/signing-secret",
      default_agent: AGENT_A,
    });
  });

  test("seatalk: sets public_base_url, and a blank value clears it (null)", () => {
    const base = {
      channel_type: "seatalk",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      signing_secret_ref: "channel/st/signing-secret",
      default_agent: AGENT_A,
    };
    const set = planChannelEdit({
      ...ST,
      config: base,
      values: { default_agent: AGENT_A, public_base_url: "https://x.trycloudflare.com/" },
    });
    expect(set.config.public_base_url).toBe("https://x.trycloudflare.com/");

    const cleared = planChannelEdit({
      ...ST,
      config: { ...base, public_base_url: "https://x.trycloudflare.com" },
      values: { default_agent: AGENT_A, public_base_url: "  " },
    });
    expect(cleared.config.public_base_url).toBeNull();
  });

  test("seatalk: a tunnel token mints a ref + secret write and turns on managed tunneling", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_A, tunnel_token: "cf-token" },
    });
    // A minted ref is opaque: `channel/<uuid4 hex>/<secret>`, carrying nothing
    // of the channel's name, so renaming the channel afterwards leaves it
    // describing nothing that can go stale. Asserted as a shape because there
    // is no value a test could name.
    expect(plan.config.tunnel_token_ref).toMatch(/^channel\/[0-9a-f]{32}\/tunnel-token$/);
    expect(plan.config.tunnel_token_ref).not.toContain(ST.name);
    expect(plan.secrets).toContainEqual({
      ref: plan.config.tunnel_token_ref,
      value: "cf-token",
    });
  });

  test("seatalk: a tunnel token rotates into the existing ref", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        tunnel_token_ref: "channel/st/tunnel-token",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_A, tunnel_token: "rotated" },
    });
    expect(plan.secrets).toEqual([{ ref: "channel/st/tunnel-token", value: "rotated" }]);
  });

  test("seatalk: switching to websocket drops the fields webhook owned", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        tunnel_token_ref: "channel/st/tunnel-token",
        public_base_url: "https://x.trycloudflare.com",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_A, delivery: "websocket", app_id: "app-1" },
    });

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "websocket",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      default_agent: AGENT_A,
    });
    expect(plan.config).not.toHaveProperty("signing_secret_ref");
    expect(plan.config).not.toHaveProperty("public_base_url");
    expect(plan.config).not.toHaveProperty("tunnel_token_ref");
  });

  test("seatalk websocket: a stale signing secret or tunnel token is never written", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: AGENT_A,
      },
      values: {
        default_agent: AGENT_A,
        delivery: "websocket",
        app_secret: "rotated",
        signing_secret: "leftover",
        tunnel_token: "leftover",
      },
    });

    // The app secret still rotates (websocket registers with it); the webhook
    // credentials do not, so no value reaches a ref the config no longer names.
    expect(plan.secrets).toEqual([{ ref: "channel/st/app-secret", value: "rotated" }]);
  });

  test("seatalk: switching back to webhook re-mints the signing-secret ref", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        delivery: "websocket",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        default_agent: AGENT_A,
      },
      values: {
        default_agent: AGENT_A,
        delivery: "webhook",
        signing_secret: "sig",
      },
    });

    expect(plan.config.delivery).toBe("webhook");
    // Credential refs are their own namespace — nothing addresses a resource
    // through one — and a minted ref now spells NEITHER the channel's name nor
    // its uid: an opaque body, and a readable tail saying which secret it is.
    // The name is what this used to spell, and what made renaming a channel
    // leave its config citing an address that no longer described it.
    expect(plan.config.signing_secret_ref).toMatch(/^channel\/[0-9a-f]{32}\/signing-secret$/);
    expect(plan.config.signing_secret_ref).not.toContain(ST.name);
    expect(plan.config.signing_secret_ref).not.toContain(ST.uid);
    expect(plan.secrets).toEqual([{ ref: plan.config.signing_secret_ref, value: "sig" }]);
  });

  test("seatalk: an unspecified delivery keeps the stored websocket choice", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        delivery: "websocket",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_B },
    });

    expect(plan.config.delivery).toBe("websocket");
    expect(plan.config.default_agent).toBe(AGENT_B);
  });

  test("seatalk: only the signing secret rotates when the app secret is blank", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: AGENT_A,
      },
      values: {
        default_agent: AGENT_A,
        app_id: "app-1",
        app_secret: "",
        signing_secret: "s2-new",
      },
    });

    expect(plan.secrets).toEqual([{ ref: "channel/st/signing-secret", value: "s2-new" }]);
  });
});
