// frontend/src/components/channel/editChannel.test.ts
//
// The edit-channel planning contract (counterpart to AddChannelDialog's
// register flow): rotating a secret writes the NEW value to the SAME
// credential ref the channel already points at (so the config never changes
// when only a secret rotates), and the config PATCH preserves every existing
// `*_ref` while only the mutable fields (bound agent, SeaTalk app id) change.
// A blank secret field means "leave it as-is" — no credential write at all.
//
// Every input below carries BOTH of the channel's strings, because they are no
// longer one: the `uid` the PATCH is addressed to, and the `name` that mints a
// credential ref and reads out in the toast. They are spelled differently on
// purpose — a fixture whose uid reads as its name would let an assertion about
// the address pass on the label.
//
// `default_agent` is an agent RESOURCE UID for the same reason (it used to be
// the chat provider key `claude_code`), so the values below are opaque too.
import { describe, expect, test } from "vitest";

import {
  honoursRequireMention,
  parseBurstWait,
  parseDirectories,
  planChannelEdit,
  storedBurstWait,
} from "./editChannel";

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

    test("a switch left at the stored value (or the default) writes nothing", () => {
      const plan = planChannelEdit({
        ...TG,
        config: { ...tgConfig, ignore_other_mentions: true },
        values: { default_agent: AGENT_A, require_mention: true, ignore_other_mentions: true },
      });

      expect(plan.config).toEqual({
        ...tgConfig,
        ignore_other_mentions: true,
        default_agent: AGENT_A,
      });
      expect("require_mention" in plan.config).toBe(false);
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
    // quiet windows, written only when they differ from what the config says
    // (an absent key reads as the backend default, 1.5s / 5s).
    const tgConfig = { channel_type: "telegram", bot_token_ref: "channel/tg/bot-token" };

    test("an absent key reads as the backend default", () => {
      expect(storedBurstWait(tgConfig, "wait_after_text_seconds")).toBe(1.5);
      expect(storedBurstWait(tgConfig, "wait_after_forward_seconds")).toBe(5);
      expect(storedBurstWait({ wait_after_text_seconds: 0 }, "wait_after_text_seconds")).toBe(0);
    });

    test("values at the defaults write nothing", () => {
      const plan = planChannelEdit({
        ...TG,
        config: tgConfig,
        values: {
          default_agent: AGENT_A,
          wait_after_text_seconds: 1.5,
          wait_after_forward_seconds: 5,
        },
      });

      expect("wait_after_text_seconds" in plan.config).toBe(false);
      expect("wait_after_forward_seconds" in plan.config).toBe(false);
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

  describe("directories for /dir", () => {
    const config = {
      channel_type: "telegram",
      bot_token_ref: "channel/tg/bot-token",
      directories: ["/srv/app"],
    };

    test("the plan carries the directories trimmed, without a trailing / or blank lines", () => {
      const { directories } = parseDirectories("  /Users/me/projects/ \n\n/srv/app\n/srv/app/\n/");
      const plan = planChannelEdit({
        ...TG,
        config,
        values: { default_agent: AGENT_A, directories },
      });

      expect(plan.config.directories).toEqual(["/Users/me/projects", "/srv/app", "/"]);
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
        values: { default_agent: AGENT_A, directories: parseDirectories("\n  \n").directories },
      });
      expect(cleared.config.directories).toEqual([]);
    });

    test("a relative path is rejected", () => {
      const parsed = parseDirectories("/srv/app\nprojects\n~/code");
      expect(parsed.invalid).toEqual(["projects", "~/code"]);
      expect(parsed.directories).toEqual(["/srv/app"]);
    });
  });
});
