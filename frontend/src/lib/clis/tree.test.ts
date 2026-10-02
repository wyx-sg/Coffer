// src/lib/clis/tree.test.ts — building, addressing and filtering a tool's command tree.
import { describe, expect, test } from "vitest";

import type { CliHelpNode } from "@/lib/api/clis";
import { buildTree, commandLine, flatten, nodeKey, pathOfKey, visibleKeys } from "./tree";

function node(path: string[], over: Partial<CliHelpNode> = {}): CliHelpNode {
  return {
    path,
    usage: null,
    description: null,
    subcommands: [],
    options: [],
    arguments: [],
    raw: "",
    structured: true,
    error: null,
    truncated: false,
    ...over,
  };
}

const NODES = [
  node([], {
    subcommands: [
      { name: "remote", summary: "Manage remotes" },
      { name: "commit", summary: "Record changes" },
    ],
  }),
  node(["remote"], { subcommands: [{ name: "add", summary: "Add a remote" }] }),
  node(["remote", "add"], {
    options: [
      {
        names: ["-f", "--fetch"],
        metavar: null,
        description: "fetch at once",
        default: null,
        required: false,
      },
    ],
  }),
  node(["commit"]),
];

describe("command tree", () => {
  test("is built from the flat list with each summary from its parent", () => {
    const root = buildTree(NODES);
    expect(root?.children.map((c) => [c.key, c.summary])).toEqual([
      ["remote", "Manage remotes"],
      ["commit", "Record changes"],
    ]);
    expect(root?.children[0]?.children[0]?.key).toBe("remote add");
    expect(flatten(root!).map((n) => n.key)).toEqual(["", "remote", "remote add", "commit"]);
  });

  test("a list with no root has no tree", () => {
    expect(buildTree([node(["x"])])).toBeNull();
    expect(buildTree([])).toBeNull();
  });

  test("addresses and command lines", () => {
    expect(nodeKey(["remote", "add"])).toBe("remote add");
    expect(pathOfKey("")).toEqual([]);
    expect(pathOfKey("remote add")).toEqual(["remote", "add"]);
    expect(commandLine("git", ["remote", "add"])).toBe("git remote add");
    expect(commandLine("git", [])).toBe("git");
  });

  test("a filter keeps matches and their ancestors", () => {
    const root = buildTree(NODES)!;
    expect(visibleKeys(root, "git", "")).toBeNull();
    expect(visibleKeys(root, "git", "  ")).toBeNull();
    expect([...visibleKeys(root, "git", "REMOTE")!].sort()).toEqual(["", "remote", "remote add"]);
    expect([...visibleKeys(root, "git", "--fetch")!].sort()).toEqual(["", "remote", "remote add"]);
    expect([...visibleKeys(root, "git", "record")!].sort()).toEqual(["", "commit"]);
    expect(visibleKeys(root, "git", "zzz")!.size).toBe(0);
  });
});
