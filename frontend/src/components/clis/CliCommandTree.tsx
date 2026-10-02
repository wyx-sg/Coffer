// src/components/clis/CliCommandTree.tsx — the Commands tab's left column: a tool's commands as a tree, with a filter.
//
// A file-tree-like list: the tool at the top, its subcommands under it, each
// row carrying the command's name, its one-line summary and — on hover or focus —
// a button that copies its full command line. Rows with children fold; a
// filter keeps the matches and the commands above them, all unfolded. The open
// command is the page's `?node=`, set by `onSelect`.
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { TruncatedText } from "@/components/ui/truncated-text";
import { commandLine, visibleKeys, type CommandTreeNode } from "@/lib/clis/tree";
import { cn } from "@/lib/utils";
import { CopyCommandButton } from "./CopyCommandButton";

/** The tree is at most four levels deep (the tool and three of subcommands). */
const INDENT = ["pl-1", "pl-5", "pl-9", "pl-[52px]"] as const;

interface Props {
  command: string;
  root: CommandTreeNode;
  selected: string;
  onSelect: (key: string) => void;
}

interface RowProps extends Omit<Props, "root"> {
  entry: CommandTreeNode;
  depth: number;
  keep: Set<string> | null;
  folded: Set<string>;
  toggle: (key: string) => void;
}

function Row({ command, entry, depth, keep, folded, toggle, selected, onSelect }: RowProps) {
  const { t } = useTranslation();
  if (keep && !keep.has(entry.key)) return null;
  const open = keep !== null || !folded.has(entry.key);
  const hasChildren = entry.children.length > 0;
  const name = entry.node.path[entry.node.path.length - 1] ?? command;
  const line = commandLine(command, entry.node.path);
  return (
    <li role="none">
      <div
        className={cn(
          "group flex items-center gap-1 rounded-md pr-1",
          INDENT[Math.min(depth, INDENT.length - 1)],
          selected === entry.key ? "bg-surface-selected" : "hover:bg-surface-hover",
        )}
      >
        {hasChildren ? (
          <button
            type="button"
            aria-label={t(open ? "clis.commands.fold" : "clis.commands.unfold", { name })}
            aria-expanded={open}
            onClick={() => toggle(entry.key)}
            className="flex size-5 shrink-0 items-center justify-center rounded-sm text-text-muted hover:text-text"
          >
            {open ? (
              <ChevronDown aria-hidden className="size-3.5" />
            ) : (
              <ChevronRight aria-hidden className="size-3.5" />
            )}
          </button>
        ) : (
          <span aria-hidden className="size-5 shrink-0" />
        )}
        <button
          type="button"
          role="treeitem"
          aria-selected={selected === entry.key}
          aria-label={line}
          onClick={() => onSelect(entry.key)}
          className="flex min-h-8 min-w-0 flex-1 flex-col justify-center py-1 text-left"
        >
          <span className="truncate font-mono text-sm text-text">{name}</span>
          {entry.summary ? (
            <TruncatedText text={entry.summary} className="text-2xs text-text-muted" />
          ) : null}
        </button>
        <span className="shrink-0 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <CopyCommandButton line={line} />
        </span>
      </div>
      {hasChildren && open ? (
        <ul role="group">
          {entry.children.map((child) => (
            <Row
              key={child.key}
              command={command}
              entry={child}
              depth={depth + 1}
              keep={keep}
              folded={folded}
              toggle={toggle}
              selected={selected}
              onSelect={onSelect}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function CliCommandTree({ command, root, selected, onSelect }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [folded, setFolded] = useState<Set<string>>(new Set());
  const keep = visibleKeys(root, command, query);
  const toggle = (key: string) =>
    setFolded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-3">
      <SearchInput
        value={query}
        onChange={setQuery}
        placeholder={t("clis.commands.search")}
        ariaLabel={t("clis.commands.search")}
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        {keep !== null && keep.size === 0 ? (
          <p className="px-2 text-xs text-text-muted">{t("clis.commands.noMatch")}</p>
        ) : (
          <ul role="tree" aria-label={t("clis.commands.treeLabel", { command })}>
            <Row
              command={command}
              entry={root}
              depth={0}
              keep={keep}
              folded={folded}
              toggle={toggle}
              selected={selected}
              onSelect={onSelect}
            />
          </ul>
        )}
      </div>
    </div>
  );
}
