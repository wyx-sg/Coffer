// frontend/src/kinds/channel/schema.affinity.test.ts
import { describe, expect, test } from "vitest";

import { addChannelFormSchema, planChannel, planChannelEdit } from "./schema";

describe("runs_on affinity", () => {
  test("planChannel binds the creating machine", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "telegram",
      name: "tg",
      bot_token: "secret-token-value",
    });
    const plan = planChannel(parsed, "M-LOCAL");
    expect(plan.config).toMatchObject({ runs_on: "M-LOCAL" });
  });

  test("planChannel without a machine stays unbound", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "telegram",
      name: "tg",
      bot_token: "secret-token-value",
    });
    const plan = planChannel(parsed, null);
    expect("runs_on" in plan.config).toBe(false);
  });

  test("planChannelEdit preserves runs_on when not touched", () => {
    const plan = planChannelEdit({
      name: "tg",
      config: { channel_type: "telegram", bot_token_ref: "r", runs_on: "M-A" },
      values: { default_agent: "claude_code" },
    });
    expect(plan.config.runs_on).toBe("M-A");
  });

  test("planChannelEdit can rebind", () => {
    const plan = planChannelEdit({
      name: "tg",
      config: { channel_type: "telegram", bot_token_ref: "r", runs_on: "M-A" },
      values: { default_agent: "claude_code", runs_on: "M-B" },
    });
    expect(plan.config.runs_on).toBe("M-B");
  });
});
