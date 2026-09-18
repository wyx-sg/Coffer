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

/**
 * The agent the new channel drives, as the dialog reads it off the picker.
 *
 * It is a UID and deliberately spelled nothing like the agent's name: the
 * config field used to hold a chat provider KEY (`claude_code`) that every
 * install shared, and the point of the uid is that a stored reference keeps
 * pointing at the same agent after someone relabels it. A fixture whose uid
 * reads as a name would let an assertion about one pass on the other.
 */
const AGENT_UID = "u-8f31c0a2";

/**
 * A credential ref, asserted as a SHAPE and never as a literal.
 *
 * A ref no longer says anything about the channel — it is
 * `channel/<uuid4 hex>/<secret>`, minted fresh — so a test cannot name the
 * value it expects, and should not want to: what the planner owes its caller
 * is that the config and the credential write agree on one opaque address whose
 * readable tail says which secret it holds. The fixture channels are still
 * called `tg` and `st`, and every assertion below goes on to check the name is
 * nowhere in the ref, which is the regression this shape exists to prevent.
 */
const refFor = (secret: string) =>
  expect.stringMatching(new RegExp(`^channel/[0-9a-f]{32}/${secret}$`));

const telegram = {
  channel_type: "telegram" as const,
  name: "tg",
  bot_token: "123:abc",
};

describe("planChannel", () => {
  test("telegram: the config carries the token REF and the bound agent, never the token", () => {
    const parsed = addChannelFormSchema.parse(telegram);
    const plan = planChannel(parsed, HERE, AGENT_UID);

    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: refFor("bot-token"),
      default_agent: AGENT_UID,
      runs_on: HERE,
    });
    // The write lands where the config points, and the channel's name is not
    // part of the address.
    expect(plan.secrets).toEqual([{ ref: plan.config.bot_token_ref, value: "123:abc" }]);
    expect(plan.config.bot_token_ref).not.toContain("/tg/");
  });

  test("seatalk: both secrets go to the store by ref, the app id stays in the config", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "seatalk",
      name: "st",
      app_id: "app-1",
      app_secret: "s1",
      signing_secret: "s2",
    });
    const plan = planChannel(parsed, HERE, AGENT_UID);

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "webhook",
      app_id: "app-1",
      app_secret_ref: refFor("app-secret"),
      signing_secret_ref: refFor("signing-secret"),
      default_agent: AGENT_UID,
      runs_on: HERE,
    });
    expect(plan.secrets).toEqual([
      { ref: plan.config.app_secret_ref, value: "s1" },
      { ref: plan.config.signing_secret_ref, value: "s2" },
    ]);
    // Two secrets, two DIFFERENT addresses — one per secret, as provider mints
    // them; a shared uuid would make a rotation of one look like the other.
    expect(plan.config.app_secret_ref).not.toBe(plan.config.signing_secret_ref);
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
    const plan = planChannel(parsed, HERE, AGENT_UID);

    expect(plan.config).toEqual({
      channel_type: "seatalk",
      delivery: "websocket",
      app_id: "app-1",
      app_secret_ref: refFor("app-secret"),
      default_agent: AGENT_UID,
      runs_on: HERE,
    });
    // Only the app secret is written — nothing lands at the signing-secret ref.
    expect(plan.secrets).toEqual([{ ref: plan.config.app_secret_ref, value: "s1" }]);
  });

  test("the binding is whatever machine is passed in, never inferred", () => {
    // Planning is pure: it reaches for no machine id of its own, so binding a
    // channel to a machine other than the caller's is a matter of the argument
    // and not of a hidden lookup.
    const parsed = addChannelFormSchema.parse(telegram);
    expect(planChannel(parsed, "machine-elsewhere", AGENT_UID).config.runs_on).toBe(
      "machine-elsewhere",
    );
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
