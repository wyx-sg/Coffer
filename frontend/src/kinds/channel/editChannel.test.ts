// frontend/src/kinds/channel/editChannel.test.ts
//
// The edit-channel planning contract (counterpart to AddChannelDialog's
// register flow): rotating a secret writes the NEW value to the SAME
// credential ref the channel already points at (so the config never changes
// when only a secret rotates), and the config PATCH preserves every existing
// `*_ref` while only the mutable fields (bound agent, SeaTalk app id) change.
// A blank secret field means "leave it as-is" — no credential write at all.
import { describe, expect, test } from "vitest";

import { planChannelEdit } from "./schema";

describe("planChannelEdit", () => {
  test("telegram: rotating the token writes the same ref, agent change patches config", () => {
    const plan = planChannelEdit({
      name: "tg",
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: "builtin",
      },
      values: { default_agent: "research", bot_token: "999:newtoken" },
    });

    expect(plan.secrets).toEqual([{ ref: "channel/tg/bot-token", value: "999:newtoken" }]);
    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      default_agent: "research",
    });
  });

  test("telegram: a blank token rotates nothing but still patches the agent", () => {
    const plan = planChannelEdit({
      name: "tg",
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: "builtin",
      },
      values: { default_agent: "research", bot_token: "" },
    });

    expect(plan.secrets).toEqual([]);
    expect(plan.config.default_agent).toBe("research");
  });

  test("telegram: preserves an unknown config field (default_agent_config)", () => {
    const plan = planChannelEdit({
      name: "tg",
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: "builtin",
        default_agent_config: { temperature: 0.2 },
      },
      values: { default_agent: "builtin", bot_token: "" },
    });

    expect(plan.config.default_agent_config).toEqual({ temperature: 0.2 });
  });

  test("seatalk: rotates both secrets to their existing refs and updates app id", () => {
    const plan = planChannelEdit({
      name: "st",
      config: {
        channel_type: "seatalk",
        app_id: "app-old",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: "builtin",
      },
      values: {
        default_agent: "builtin",
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
      app_id: "app-new",
      app_secret_ref: "channel/st/app-secret",
      signing_secret_ref: "channel/st/signing-secret",
      default_agent: "builtin",
    });
  });

  test("seatalk: sets public_base_url, and a blank value clears it (null)", () => {
    const base = {
      channel_type: "seatalk",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      signing_secret_ref: "channel/st/signing-secret",
      default_agent: "builtin",
    };
    const set = planChannelEdit({
      name: "st",
      config: base,
      values: { default_agent: "builtin", public_base_url: "https://x.trycloudflare.com/" },
    });
    expect(set.config.public_base_url).toBe("https://x.trycloudflare.com/");

    const cleared = planChannelEdit({
      name: "st",
      config: { ...base, public_base_url: "https://x.trycloudflare.com" },
      values: { default_agent: "builtin", public_base_url: "  " },
    });
    expect(cleared.config.public_base_url).toBeNull();
  });

  test("seatalk: a tunnel token mints a ref + secret write and turns on managed tunneling", () => {
    const plan = planChannelEdit({
      name: "st",
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: "claude-code",
      },
      values: { default_agent: "claude-code", tunnel_token: "cf-token" },
    });
    expect(plan.config.tunnel_token_ref).toBe("channel/st/tunnel-token");
    expect(plan.secrets).toContainEqual({ ref: "channel/st/tunnel-token", value: "cf-token" });
  });

  test("seatalk: a tunnel token rotates into the existing ref", () => {
    const plan = planChannelEdit({
      name: "st",
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        tunnel_token_ref: "channel/st/tunnel-token",
        default_agent: "claude-code",
      },
      values: { default_agent: "claude-code", tunnel_token: "rotated" },
    });
    expect(plan.secrets).toEqual([{ ref: "channel/st/tunnel-token", value: "rotated" }]);
  });

  test("seatalk: only the signing secret rotates when the app secret is blank", () => {
    const plan = planChannelEdit({
      name: "st",
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        signing_secret_ref: "channel/st/signing-secret",
        default_agent: "builtin",
      },
      values: {
        default_agent: "builtin",
        app_id: "app-1",
        app_secret: "",
        signing_secret: "s2-new",
      },
    });

    expect(plan.secrets).toEqual([{ ref: "channel/st/signing-secret", value: "s2-new" }]);
  });
});
