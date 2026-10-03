import { describe, expect, test } from "vitest";
import { contentBlock } from "./contentBlock";
import { unfinishedWork } from "./stopped";

const use = (name: string, id = "t1") =>
  contentBlock({ type: "tool_use", tool_use_id: id, tool_name: name });
const result = (id = "t1") => contentBlock({ type: "tool_result", tool_use_id: id });

describe("unfinishedWork", () => {
  test.each(["Edit", "Write", "MultiEdit", "NotebookEdit", "file_change"])(
    "a running %s left an edit",
    (name) => {
      expect(unfinishedWork([use(name)])).toBe("edit");
    },
  );
  test.each(["Bash", "shell"])("a running %s left a command", (name) => {
    expect(unfinishedWork([use(name)])).toBe("command");
  });
  test("another running tool says nothing more", () => {
    expect(unfinishedWork([use("Grep")])).toBeNull();
  });
  test("a call that already returned is not unfinished", () => {
    expect(unfinishedWork([use("Edit"), result()])).toBeNull();
  });
  test("a reply with no tool call is not either", () => {
    expect(unfinishedWork([contentBlock({ type: "text", text: "hi" })])).toBeNull();
  });
  test("the last running call decides", () => {
    expect(unfinishedWork([use("Edit", "a"), use("Bash", "b")])).toBe("command");
  });
});
