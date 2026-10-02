// src/lib/clis/tree.ts — pure helpers for a tool's command tree: build it from the flat node list, address a node, filter it, word one command line.
//
// The daemon sends the nodes flat (each with its `path`, empty for the tool
// itself); the Commands tab shows them as a tree. A node is addressed by its
// path joined with spaces (`commit`, `remote add`; the tool itself is the empty
// string), which is also what the page's `?node=` search param holds.
import type { CliHelpNode } from "@/lib/api/clis";

export interface CommandTreeNode {
  node: CliHelpNode;
  /** `path` joined with spaces; "" for the tool itself. */
  key: string;
  /** What the parent's list says this command does. */
  summary: string | null;
  children: CommandTreeNode[];
}

export const nodeKey = (path: readonly string[]): string => path.join(" ");

export const pathOfKey = (key: string): string[] => (key === "" ? [] : key.split(" "));

/** `git commit`: the tool and the path to the node, as typed. */
export const commandLine = (command: string, path: readonly string[]): string =>
  [command, ...path].join(" ");

/** The tree of `nodes` (the tool itself at the root), or null when there are none. */
export function buildTree(nodes: readonly CliHelpNode[]): CommandTreeNode | null {
  const byKey = new Map<string, CommandTreeNode>();
  for (const node of nodes) {
    byKey.set(nodeKey(node.path), { node, key: nodeKey(node.path), summary: null, children: [] });
  }
  const root = byKey.get("") ?? null;
  for (const entry of byKey.values()) {
    if (entry.key === "") continue;
    const parent = byKey.get(nodeKey(entry.node.path.slice(0, -1)));
    if (!parent) continue;
    const name = entry.node.path[entry.node.path.length - 1];
    entry.summary = parent.node.subcommands.find((s) => s.name === name)?.summary ?? null;
    parent.children.push(entry);
  }
  return root;
}

/** The keys to show for `query`: every node whose command line, summary,
 *  description or option names contain it, with their ancestors. `null` when
 *  the query is empty (everything shows). */
export function visibleKeys(
  root: CommandTreeNode,
  command: string,
  query: string,
): Set<string> | null {
  const q = query.trim().toLowerCase();
  if (q === "") return null;
  const keep = new Set<string>();
  const walk = (entry: CommandTreeNode, ancestors: string[]) => {
    const { node } = entry;
    const haystack = [
      commandLine(command, node.path),
      entry.summary ?? "",
      node.description ?? "",
      ...node.options.flatMap((o) => [...o.names, o.description ?? ""]),
    ]
      .join("\n")
      .toLowerCase();
    if (haystack.includes(q)) {
      keep.add(entry.key);
      for (const a of ancestors) keep.add(a);
    }
    for (const child of entry.children) walk(child, [...ancestors, entry.key]);
  };
  walk(root, []);
  return keep;
}

/** Every node of the tree in reading order, parents before their children. */
export function flatten(root: CommandTreeNode): CommandTreeNode[] {
  return [root, ...root.children.flatMap(flatten)];
}
