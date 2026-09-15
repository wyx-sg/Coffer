// frontend/src/components/channel/schema.test.ts
//
// The create-side planning contract: validated form values become the resource
// config plus the credential-store writes, with secrets reaching the store by
// ref only. A channel binds an agent and nothing more — every model that agent
// offers stays available, and the model is switched in chat with /model.
//
// It also binds a MACHINE: `runs_on` is in every config below, because a
// channel created from this machine and bound to nobody would be a bot no
// daemon ever starts.
import { describe, expect, test } from "vitest";

import { addChannelFormSchema, planChannel } from "./schema";

/** This machine's id, as the dialog reads it off `GET /sync/status`. */
const HERE = "machine-here";

const telegram = {
  channel_type: "telegram" as const,
  name: "tg",
  bot_token: "123:abc",
};

describe("planChannel", () => {
  test("telegram: the config carries the token REF and the bound agent, never the token", () => {
    const parsed = addChannelFormSchema.parse(telegram);
    const plan = planChannel(parsed, HERE);

    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      default_agent: "claude_code",
      runs_on: HERE,
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
    const plan = planChannel(parsed, HERE);

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "webhook",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      signing_secret_ref: "channel/st/signing-secret",
      default_agent: "claude_code",
      runs_on: HERE,
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
    const plan = planChannel(parsed, HERE);

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "websocket",
      app_id: "app-1",
      app_secret_ref: "channel/st/app-secret",
      default_agent: "claude_code",
      runs_on: HERE,
    });
    // Only the app secret is written — nothing lands at the signing-secret ref.
    expect(plan.secrets).toEqual([{ ref: "channel/st/app-secret", value: "s1" }]);
  });

  test("the binding is whatever machine is passed in, never inferred", () => {
    // Planning is pure: it reaches for no machine id of its own, so binding a
    // channel to a machine other than the caller's is a matter of the argument
    // and not of a hidden lookup.
    const parsed = addChannelFormSchema.parse(telegram);
    expect(planChannel(parsed, "machine-elsewhere").config.runs_on).toBe("machine-elsewhere");
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
