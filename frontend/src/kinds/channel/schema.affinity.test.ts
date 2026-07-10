// frontend/src/kinds/channel/schema.affinity.test.ts
//
// Runtime affinity (ADR-045) no longer lives in config at all: `runs_on` is
// inert (superseded by the resource's `scope`), and planChannel/planChannelEdit
// must never write it. The create-time auto-bind-to-this-machine now happens
// as a separate PUT .../scope call — see AddChannelDialog.test.tsx.
import { describe, expect, test } from "vitest";

import { addChannelFormSchema, planChannel, planChannelEdit } from "./schema";

describe("runs_on is dead config", () => {
  test("planChannel never embeds runs_on", () => {
    const parsed = addChannelFormSchema.parse({
      channel_type: "telegram",
      name: "tg",
      bot_token: "secret-token-value",
    });
    const plan = planChannel(parsed);
    expect("runs_on" in plan.config).toBe(false);
  });

  test("planChannelEdit preserves an existing runs_on value verbatim (dead field, not stripped)", () => {
    // A pre-migration config may still carry a stale `runs_on` (Pydantic
    // still emits the deprecated field). planChannelEdit spreads the existing
    // config through unmodified — it must neither strip nor write to it.
    const plan = planChannelEdit({
      name: "tg",
      config: { channel_type: "telegram", bot_token_ref: "r", runs_on: "M-A" },
      values: { default_agent: "claude_code" },
    });
    expect(plan.config.runs_on).toBe("M-A");
  });
});
