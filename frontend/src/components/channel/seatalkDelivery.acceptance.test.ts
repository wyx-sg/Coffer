// frontend/src/components/channel/seatalkDelivery.acceptance.test.ts
//
// spec channels/seatalk "Choose exactly one inbound delivery per channel": a
// SeaTalk channel with no `delivery` field is a webhook channel, and switching
// it to websocket clears every field the webhook method owns. The switch is an
// edit, so the path under test is the edit planner the Channels page PATCHes.
import { expect } from "vitest";

import { acceptance } from "@/test/acceptance";

import { planChannelEdit } from "./editChannel";

const CHANNEL = { uid: "u-9f1e2d3c", name: "st" };
const AGENT = "u-a17c4e90";

/** A channel registered before websocket delivery existed: no `delivery` key. */
const LEGACY_WEBHOOK_CONFIG = {
  channel_type: "seatalk",
  app_id: "app-1",
  app_secret_ref: "channel/st/app-secret",
  signing_secret_ref: "channel/st/signing-secret",
  public_base_url: "https://bot.example.com",
  tunnel_token_ref: "channel/st/tunnel-token",
  default_agent: AGENT,
};

acceptance(
  "channels/seatalk",
  "switching a channel to websocket delivery clears its webhook fields",
  () => {
    // Read as-is (no delivery chosen in the edit): the absent field means webhook,
    // and every webhook field is kept.
    const unchanged = planChannelEdit({
      ...CHANNEL,
      config: LEGACY_WEBHOOK_CONFIG,
      values: { default_agent: AGENT },
    });
    expect(unchanged.config.delivery).toBe("webhook");
    expect(unchanged.config.signing_secret_ref).toBe("channel/st/signing-secret");
    expect(unchanged.config.public_base_url).toBe("https://bot.example.com");
    expect(unchanged.config.tunnel_token_ref).toBe("channel/st/tunnel-token");

    // Switched to websocket: the fields webhook owned are gone.
    const switched = planChannelEdit({
      ...CHANNEL,
      config: LEGACY_WEBHOOK_CONFIG,
      values: { default_agent: AGENT, delivery: "websocket" },
    });
    expect(switched.config.delivery).toBe("websocket");
    expect(switched.config).not.toHaveProperty("signing_secret_ref");
    expect(switched.config).not.toHaveProperty("public_base_url");
    expect(switched.config).not.toHaveProperty("tunnel_token_ref");
    // What both methods need survives the switch.
    expect(switched.config.app_id).toBe("app-1");
    expect(switched.config.app_secret_ref).toBe("channel/st/app-secret");
  },
);
