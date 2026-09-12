// frontend/src/kinds/channel/schema.test.ts
//
// The create-side planning contract: validated form values become the resource
// config plus the credential-store writes, with secrets reaching the store by
// ref only. A channel binds an agent and nothing more — every model that agent
// offers stays available, and the model is switched in chat with /model.
import { describe, expect, test } from "vitest";

import { addChannelFormSchema, planChannel } from "./schema";

const telegram = {
  channel_type: "telegram" as const,
  name: "tg",
  bot_token: "123:abc",
};

describe("planChannel", () => {
  test("telegram: the config carries the token REF and the bound agent, never the token", () => {
    const parsed = addChannelFormSchema.parse(telegram);
    const plan = planChannel(parsed);

    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      default_agent: "claude_code",
    });
    expect(plan.secrets).toEqual([{ ref: "channel/tg/bot-token", value: "123:abc" }]);
  });

  test("seatalk: both secrets go to the store by ref, the app id stays in the config", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "seatalk",
      name: "st",
      app_id: "app-1",
      app_secret: "s1",
      signing_secret: "s2",
    });
    const plan = planChannel(parsed);

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "webhook",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      signing_secret_ref: "channel/st/signing-secret",
      default_agent: "claude_code",
    });
    expect(plan.secrets).toEqual([
      { ref: "channel/st/app-secret", value: "s1" },
      { ref: "channel/st/signing-secret", value: "s2" },
    ]);
  });

  test("seatalk: delivery defaults to webhook when the form omits it", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "seatalk",
      name: "st",
      app_id: "app-1",
      app_secret: "s1",
      signing_secret: "s2",
    });
    expect(parsed.channel_type === "seatalk" && parsed.delivery).toBe("webhook");
  });

  test("seatalk websocket: no signing secret, no public URL, no tunnel ref", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "seatalk",
      name: "st",
      delivery: "websocket",
      app_id: "app-1",
      app_secret: "s1",
    });
    const plan = planChannel(parsed);

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "websocket",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      default_agent: "claude_code",
    });
    // Only the app secret is written — nothing lands at the signing-secret ref.
    expect(plan.secrets).toEqual([{ ref: "channel/st/app-secret", value: "s1" }]);
  });
});

describe("addChannelFormSchema (the backend's cross-field rule, mirrored)", () => {
  const seatalk = {
    channel_type: "seatalk" as const,
    name: "st",
    app_id: "app-1",
    app_secret: "s1",
  };

  test("webhook delivery requires a signing secret", () => {
    const parsed = addChannelFormSchema.safeParse({ ...seatalk, delivery: "webhook" });
    expect(parsed.success).toBe(false);
    expect(parsed.error?.issues.map((i) => i.path.join("."))).toContain("signing_secret");
  });

  test("websocket delivery accepts app id + app secret alone", () => {
    expect(addChannelFormSchema.safeParse({ ...seatalk, delivery: "websocket" }).success).toBe(
      true,
    );
  });

  test("websocket delivery forbids every webhook-only field", () => {
    for (const field of ["signing_secret", "public_base_url", "tunnel_token"]) {
      const parsed = addChannelFormSchema.safeParse({
        ...seatalk,
        delivery: "websocket",
        [field]: "x",
      });
      expect(parsed.success, field).toBe(false);
      expect(parsed.error?.issues.map((i) => i.path.join("."))).toContain(field);
    }
  });
});
