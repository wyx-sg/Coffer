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
});
