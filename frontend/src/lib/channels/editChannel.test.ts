// frontend/src/lib/channels/editChannel.test.ts
//
// The edit-channel planning contract (counterpart to AddChannelDialog's
// register flow): rotating a secret writes the NEW value to the SAME
// secret ref the channel already points at (so the config never changes
// when only a secret rotates), and the config PATCH preserves every existing
// `*_ref` while only the mutable fields (bound agent, SeaTalk app id) change.
// A blank secret field means "leave it as-is" — no secret write at all.
//
// Every input below carries BOTH of the channel's strings, because they are no
// longer one: the `uid` the PATCH is addressed to, and the `name` that mints a
// secret ref and reads out in the toast. They are spelled differently on
// purpose — a fixture whose uid reads as its name would let an assertion about
// the address pass on the label.
//
// `default_agent` is an agent RESOURCE UID for the same reason (it used to be
// the chat provider key `claude_code`), so the values below are opaque too.
import { describe, expect, test } from "vitest";

import {
  honoursRequireMention,
  normaliseDirectory,
  planChannelEdit,
  storedDefaultDirectory,
} from "@/lib/channels/editChannel";
import {
  parseBurstWait,
  parseIdleHours,
  parseNotifyAfter,
} from "@/components/channel/channelTurnSettings";

/** The two channels every case below edits: a uid to address, a name to read. */
const TG = { uid: "u-3d9a1f77", name: "tg" };
const ST = { uid: "u-c0be4512", name: "st" };

/** Agents the bindings point at — uids, never the names they display under. */
const AGENT_A = "u-a17c4e90";
const AGENT_B = "u-b52f08d3";

describe("planChannelEdit", () => {
  test("the plan carries the uid to address and the name to read out", () => {
    // Both, and separately. The apply PATCHes `/resources/{uid}` and toasts the
    // name, so a plan that carried one of them would either address the wrong
    // row or tell the user about a channel by an id they cannot read.
    const plan = planChannelEdit({
      ...TG,
      config: { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" },
      values: { default_agent: AGENT_A },
    });

    expect(plan.uid).toBe(TG.uid);
    expect(plan.name).toBe(TG.name);
  });

  test("telegram: rotating the token writes the same ref, agent change patches config", () => {
    const plan = planChannelEdit({
      ...TG,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_B, bot_token: "999:newtoken" },
    });

    expect(plan.secrets).toEqual([{ ref: "channel/tg/bot-token", value: "999:newtoken" }]);
    expect(plan.config).toEqual({
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      default_agent: AGENT_B,
    });
  });

  test("telegram: a blank token rotates nothing but still patches the agent", () => {
    const plan = planChannelEdit({
      ...TG,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_B, bot_token: "" },
    });

    expect(plan.secrets).toEqual([]);
    expect(plan.config.default_agent).toBe(AGENT_B);
  });

  test("telegram: preserves an unknown config field (default_agent_config)", () => {
    const plan = planChannelEdit({
      ...TG,
      config: {
        channel_type: "telegram",
        bot_token_ref: "channel/tg/bot-token",
        default_agent: AGENT_A,
        default_agent_config: { temperature: 0.2 },
      },
      values: { default_agent: AGENT_A, bot_token: "" },
    });

    expect(plan.config.default_agent_config).toEqual({ temperature: 0.2 });
  });

  test("seatalk: rotates the app secret to its existing ref and updates app id", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-old",
        app_secret_ref: "channel/st/app-secret",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_A, app_id: "app-new", app_secret: "s1" },
    });

    expect(plan.secrets).toEqual([{ ref: "channel/st/app-secret", value: "s1" }]);
    expect(plan.config).toEqual({
      channel_type: "seatalk",
      app_id: "app-new",
      app_secret_ref: "channel/st/app-secret",
      default_agent: AGENT_A,
    });
  });

  test("seatalk: a blank app secret rotates nothing but still patches the agent", () => {
    const plan = planChannelEdit({
      ...ST,
      config: {
        channel_type: "seatalk",
        app_id: "app-1",
        app_secret_ref: "channel/st/app-secret",
        default_agent: AGENT_A,
      },
      values: { default_agent: AGENT_B, app_id: "app-1", app_secret: "" },
    });

    expect(plan.secrets).toEqual([]);
    expect(plan.config.default_agent).toBe(AGENT_B);
  });

  describe("group gating", () => {
    const tgConfig = { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" };

    test("telegram: flipping both switches writes both keys", () => {
      const plan = planChannelEdit({
        ...TG,
        config: tgConfig,
        values: { default_agent: AGENT_A, require_mention: false, ignore_other_mentions: true },
      });

      expect(plan.config.require_mention).toBe(false);
      expect(plan.config.ignore_other_mentions).toBe(true);
    });

    test("a switch left at the stored value writes nothing new", () => {
      const plan = planChannelEdit({
        ...TG,
        config: { ...tgConfig, require_mention: true, ignore_other_mentions: true },
        values: { default_agent: AGENT_A, require_mention: true, ignore_other_mentions: true },
      });

      expect(plan.config).toEqual({
        ...tgConfig,
        require_mention: true,
        ignore_other_mentions: true,
        default_agent: AGENT_A,
      });
    });

    test("seatalk: require_mention is never written — SeaTalk only delivers @mentions", () => {
      expect(honoursRequireMention("seatalk")).toBe(false);
      expect(honoursRequireMention("telegram")).toBe(true);
      const plan = planChannelEdit({
        ...ST,
        config: { channel_type: "seatalk", app_id: "a", app_secret_ref: "channel/st/app-secret" },
        values: { default_agent: AGENT_A, require_mention: false, ignore_other_mentions: true },
      });

      expect("require_mention" in plan.config).toBe(false);
      expect(plan.config.ignore_other_mentions).toBe(true);
    });
  });

  describe("message batching", () => {
    // spec channels "Take a burst of messages as one turn": two per-channel
    // quiet windows, written only when they differ from what the config holds.
    const tgConfig = {
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      wait_after_text_seconds: 1.5,
      wait_after_forward_seconds: 5,
    };

    test("values equal to the stored ones write nothing new", () => {
      const plan = planChannelEdit({
        ...TG,
        config: tgConfig,
        values: {
          default_agent: AGENT_A,
          wait_after_text_seconds: 1.5,
          wait_after_forward_seconds: 5,
        },
      });

      expect(plan.config.wait_after_text_seconds).toBe(1.5);
      expect(plan.config.wait_after_forward_seconds).toBe(5);
      expect(Object.keys(plan.config).sort()).toEqual(
        [...Object.keys(tgConfig), "default_agent"].sort(),
      );
    });

    test("a changed window writes its key, an unchanged stored one is kept as-is", () => {
      const plan = planChannelEdit({
        ...ST,
        config: {
          channel_type: "seatalk",
          app_id: "a",
          app_secret_ref: "channel/st/app-secret",
          wait_after_forward_seconds: 8,
        },
        values: {
          default_agent: AGENT_A,
          wait_after_text_seconds: 0,
          wait_after_forward_seconds: 8,
        },
      });

      expect(plan.config.wait_after_text_seconds).toBe(0);
      expect(plan.config.wait_after_forward_seconds).toBe(8);
    });

    test("parseBurstWait accepts 0..60 seconds and rejects the rest", () => {
      expect(parseBurstWait("0")).toBe(0);
      expect(parseBurstWait("2.5")).toBe(2.5);
      expect(parseBurstWait("60")).toBe(60);
      expect(parseBurstWait("")).toBeNull();
      expect(parseBurstWait("  ")).toBeNull();
      expect(parseBurstWait("-1")).toBeNull();
      expect(parseBurstWait("60.5")).toBeNull();
      expect(parseBurstWait("abc")).toBeNull();
    });
  });

  describe("replies", () => {
    // Two per-channel settings: list each step under the live status line
    // (show_steps) and the completion ping threshold (notify_after_seconds,
    // 0 = off).
    const config = {
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      show_steps: true,
      notify_after_seconds: 90,
    };

    test("values equal to the stored ones are not rewritten", () => {
      const plan = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, show_steps: true, notify_after_seconds: 90 },
      });

      expect(plan.config).toEqual({ ...config, default_agent: AGENT_A });
    });

    test("changed values write their keys, and 0 turns the ping off", () => {
      const plan = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, show_steps: false, notify_after_seconds: 0 },
      });

      expect(plan.config.show_steps).toBe(false);
      expect(plan.config.notify_after_seconds).toBe(0);
    });

    test("an unchanged stored value is kept as-is", () => {
      const stored = { ...config, show_steps: false, notify_after_seconds: 300 };
      const plan = planChannelEdit({
        ...TG,
        config: stored,
        values: { default_agent: AGENT_A, show_steps: false, notify_after_seconds: 300 },
      });

      expect(plan.config.show_steps).toBe(false);
      expect(plan.config.notify_after_seconds).toBe(300);
    });

    test("parseNotifyAfter accepts 0..3600 seconds and rejects the rest", () => {
      expect(parseNotifyAfter("0")).toBe(0);
      expect(parseNotifyAfter("90")).toBe(90);
      expect(parseNotifyAfter("3600")).toBe(3600);
      expect(parseNotifyAfter("")).toBeNull();
      expect(parseNotifyAfter("  ")).toBeNull();
      expect(parseNotifyAfter("-1")).toBeNull();
      expect(parseNotifyAfter("3601")).toBeNull();
      expect(parseNotifyAfter("abc")).toBeNull();
    });
  });

  describe("idle period", () => {
    // spec channels "Open a new conversation after an idle period": hours of
    // quiet before a chat's next message opens a new conversation; 0 = never.
    const config = {
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      new_conversation_after_idle_hours: 24,
    };

    test("a changed period is written, an unchanged one is kept, 0 turns it off", () => {
      const changed = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, new_conversation_after_idle_hours: 6 },
      });
      expect(changed.config.new_conversation_after_idle_hours).toBe(6);

      const never = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, new_conversation_after_idle_hours: 0 },
      });
      expect(never.config.new_conversation_after_idle_hours).toBe(0);

      const same = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, new_conversation_after_idle_hours: 24 },
      });
      expect(same.config.new_conversation_after_idle_hours).toBe(24);
    });

    test("parseIdleHours accepts 0..8760 hours and rejects the rest", () => {
      expect(parseIdleHours("0")).toBe(0);
      expect(parseIdleHours("1.5")).toBe(1.5);
      expect(parseIdleHours("24")).toBe(24);
      expect(parseIdleHours("8760")).toBe(8760);
      expect(parseIdleHours("")).toBeNull();
      expect(parseIdleHours("-1")).toBeNull();
      expect(parseIdleHours("8761")).toBeNull();
      expect(parseIdleHours("abc")).toBeNull();
    });
  });

  describe("directories for /dir", () => {
    const config = {
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      directories: ["/srv/app"],
    };

    test("a typed directory is normalised, and a relative one is refused", () => {
      expect(normaliseDirectory("  /Users/me/projects/ ")).toBe("/Users/me/projects");
      expect(normaliseDirectory("/")).toBe("/");
      expect(normaliseDirectory("projects")).toBeNull();
      expect(normaliseDirectory("~/code")).toBeNull();
    });

    test("an unchanged list is not rewritten, and an empty one clears it", () => {
      const same = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, directories: ["/srv/app"] },
      });
      expect(same.config.directories).toEqual(["/srv/app"]);

      const cleared = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, directories: [] },
      });
      expect(cleared.config.directories).toEqual([]);
    });

    test("the default directory is written into the default agent config and cleared from it", () => {
      const withModel = { ...config, default_agent_config: { model: "opus" } };
      const set = planChannelEdit({
        ...TG,
        config: withModel,
        values: { default_agent: AGENT_A, default_directory: "/srv/app" },
      });
      expect(set.config.default_agent_config).toEqual({ model: "opus", cwd: "/srv/app" });
      expect(storedDefaultDirectory(set.config)).toBe("/srv/app");

      const cleared = planChannelEdit({
        ...TG,
        config: { ...config, default_agent_config: { cwd: "/srv/app" } },
        values: { default_agent: AGENT_A, default_directory: null },
      });
      expect(cleared.config.default_agent_config).toBeNull();
    });
  });
});
