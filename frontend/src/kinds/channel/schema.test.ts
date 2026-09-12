// frontend/src/kinds/channel/schema.test.ts
//
// The create-side half of the channel's model curation (spec channels FR-071):
// what reaches the registered config, and the one rule the form mirrors from
// the backend — a default model outside a non-empty allowed range is refused,
// because a channel must not open conversations on a model it then refuses.
import { describe, expect, test } from "vitest";

import { defaultModelOutOfRange } from "./modelCuration";
import { addChannelFormSchema, planChannel } from "./schema";

const telegram = {
  channel_type: "telegram" as const,
  name: "tg",
  bot_token: "123:abc",
};

describe("channel model curation", () => {
  test("an unconfigured channel carries neither key — the backend's own defaults", () => {
    const parsed = addChannelFormSchema.parse({ ...telegram, default_model: "", models: [] });
    const plan = planChannel(parsed);

    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      default_agent: "claude_code",
    });
  });

  test("a configured channel registers both, in the order they were ticked", () => {
    const parsed = addChannelFormSchema.parse({
      ...telegram,
      default_model: "claude-opus-5",
      models: ["claude-opus-5", "claude-haiku-4-5"],
    });

    expect(planChannel(parsed).config).toMatchObject({
      default_model: "claude-opus-5",
      models: ["claude-opus-5", "claude-haiku-4-5"],
    });
  });

  test("a default outside a non-empty range fails validation", () => {
    const parsed = addChannelFormSchema.safeParse({
      ...telegram,
      default_model: "claude-haiku-4-5",
      models: ["claude-opus-5"],
    });

    expect(parsed.success).toBe(false);
    expect(parsed.error?.issues[0].path).toEqual(["default_model"]);
  });

  test("an EMPTY range restricts nothing, so any default passes", () => {
    // Empty means NOT CURATED, never "no models" — an id the catalogue does not
    // list is still handed to the CLI verbatim.
    expect(
      addChannelFormSchema.safeParse({ ...telegram, default_model: "some-new-model", models: [] })
        .success,
    ).toBe(true);
    expect(defaultModelOutOfRange("some-new-model", [])).toBe(false);
    expect(defaultModelOutOfRange("", ["claude-opus-5"])).toBe(false);
    expect(defaultModelOutOfRange("claude-opus-5", ["claude-opus-5"])).toBe(false);
    expect(defaultModelOutOfRange("claude-haiku-4-5", ["claude-opus-5"])).toBe(true);
  });

  test("seatalk carries the same two fields", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "seatalk",
      name: "st",
      app_id: "app-1",
      app_secret: "s1",
      signing_secret: "s2",
      default_model: "claude-opus-5",
      models: ["claude-opus-5"],
    });

    expect(planChannel(parsed).config).toMatchObject({
      channel_type: "seatalk",
      default_model: "claude-opus-5",
      models: ["claude-opus-5"],
    });
  });
});
