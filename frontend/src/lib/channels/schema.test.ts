// frontend/src/lib/channels/schema.test.ts
//
// The create-side planning contract: validated form values become the resource
// config plus the secret-store writes, with secrets reaching the store by
// ref only. A channel binds an agent and nothing more — every model that agent
// offers stays available, and the model is switched in chat with /model.
//
// It also binds a MACHINE: `runs_on` is in every config below, because a
// channel created from this machine and bound to nobody would be a bot no
// daemon ever starts.
import { describe, expect, test } from "vitest";

import { addChannelFormSchema, channelSlug, planChannel } from "@/lib/channels/schema";

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
 * A secret ref, asserted as a SHAPE and never as a literal.
 *
 * A ref no longer says anything about the channel — it is
 * `secret/<uuid4 hex>`, minted fresh — so a test cannot name the
 * value it expects, and should not want to: what the planner owes its caller
 * is that the config and the secret write agree on one opaque address whose
 * readable tail says which secret it holds. The fixture channels are still
 * called `tg` and `st`, and every assertion below goes on to check the name is
 * nowhere in the ref, which is the regression this shape exists to prevent.
 */
const refFor = () => expect.stringMatching(/^secret\/[0-9a-f]{32}$/);

/** A pasted value, as the secret field holds it: written under its minted id, named by `label`. */
const pasted = (value: string, label = "pasted") => ({
  kind: "new" as const,
  name: "0123456789abcdef0123456789abcdef",
  label,
  value,
});

const telegram = {
  channel_type: "telegram" as const,
  name: "tg",
  bot_token: pasted("123:abc", "tg Bot token"),
};

describe("planChannel", () => {
  test("telegram: the config carries the token REF and the bound agent, never the token", () => {
    const parsed = addChannelFormSchema.parse(telegram);
    const plan = planChannel(parsed, HERE, AGENT_UID);

    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: refFor(),
      default_agent: AGENT_UID,
      runs_on: HERE,
    });
    // The write lands where the config points, and the channel's name is not
    // part of the address.
    expect(plan.secrets).toEqual([
      { ref: plan.config.bot_token_ref, value: "123:abc", label: "tg Bot token" },
    ]);
    expect(plan.config.bot_token_ref).not.toContain("/tg/");
  });

  test("seatalk: the app secret goes to the store by ref, the app id stays in the config", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "seatalk",
      name: "st",
      app_id: "app-1",
      app_secret: pasted("s1"),
    });
    const plan = planChannel(parsed, HERE, AGENT_UID);

    // App id and app secret are the whole of SeaTalk's config: the channel
    // dials out over a websocket, so there is no signature, public URL or
    // tunnel to carry.
    expect(plan.config).toEqual({
      channel_type: "seatalk",
      app_id: "app-1",
      app_secret_ref: refFor(),
      default_agent: AGENT_UID,
      runs_on: HERE,
    });
    expect(plan.secrets).toEqual([
      { ref: plan.config.app_secret_ref, value: "s1", label: "pasted" },
    ]);
  });

  test("a stored secret is cited as it is, and nothing is written", () => {
    const parsed = addChannelFormSchema.parse({
      ...telegram,
      bot_token: { kind: "stored", name: "a1".repeat(16) },
    });
    const plan = planChannel(parsed, HERE, AGENT_UID);
    expect(plan.config.bot_token_ref).toBe(`secret/${"a1".repeat(16)}`);
    expect(plan.secrets).toEqual([]);
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

describe("addChannelFormSchema", () => {
  const seatalk = {
    channel_type: "seatalk" as const,
    name: "st",
    app_id: "app-1",
    app_secret: pasted("s1"),
  };

  test("seatalk accepts app id + app secret alone", () => {
    expect(addChannelFormSchema.safeParse(seatalk).success).toBe(true);
  });

  test("seatalk requires both the app id and the app secret", () => {
    for (const field of ["app_id", "app_secret"]) {
      const empty = field === "app_id" ? "" : null;
      const parsed = addChannelFormSchema.safeParse({ ...seatalk, [field]: empty });
      expect(parsed.success, field).toBe(false);
      expect(parsed.error?.issues.map((i) => i.path.join("."))).toContain(field);
    }
  });
});

describe("channelSlug", () => {
  test("derives a resource name from any display name", () => {
    expect(channelSlug("Team bot")).toBe("team-bot");
    expect(channelSlug("  Ops · alerts!  ")).toBe("ops-alerts");
    expect(channelSlug("团队")).toBe("channel");
  });

  test("steps past names already taken", () => {
    expect(channelSlug("Team bot", ["team-bot", "team-bot-2"])).toBe("team-bot-3");
  });
});
