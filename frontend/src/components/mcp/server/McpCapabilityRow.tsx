// src/components/mcp/server/McpCapabilityRow.tsx — one row of the Resources or Prompts tab, and the details it opens to (design 4.1.11, 4.1.12).
//
// Opens the way a tool row does: a click or Enter anywhere but its box and
// switch, a chevron beside the name, one row open at a time. The details sit
// in a full-width cell under the row.
import { ChevronRight } from "lucide-react";

import { TruncatedText } from "@/components/ui/truncated-text";
import { cn } from "@/lib/utils";
import { ToggleSwitch } from "../CapabilityRowCells";
import { RowSelectBox, type CapabilitySelection } from "./CapabilityToolbar";
import type { CapabilityRow } from "./McpCapabilityTab";
import { McpPromptDetail } from "./McpPromptDetail";
import { McpResourceDetail } from "./McpResourceDetail";

interface Props {
  serverUid: string;
  kind: "resource" | "prompt";
  row: CapabilityRow;
  uses: number;
  selection: CapabilitySelection;
  expanded: boolean;
  onToggle: () => void;
}

const COLUMNS = 5;

export function McpCapabilityRow({
  serverUid,
  kind,
  row,
  uses,
  selection,
  expanded,
  onToggle,
}: Props) {
  return (
    <>
      <tr
        aria-expanded={expanded}
        tabIndex={0}
        className={cn(
          "group h-12 cursor-pointer hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
          !expanded && "border-b border-border-subtle",
        )}
        onClick={onToggle}
        onKeyDown={(e) => {
          // The box and the switch inside handle their own keys.
          if (e.target !== e.currentTarget) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        <td className="py-2 pl-2">
          <RowSelectBox selection={selection} rowKey={row.key} name={row.key} />
        </td>
        <td className="py-2 text-center">
          <ToggleSwitch serverUid={serverUid} kind={kind} row={row} />
        </td>
        <td className="py-2 pr-3">
          <span className="flex items-center gap-1">
            <TruncatedText text={row.key} mono className="text-xs font-semibold" />
            <ChevronRight
              aria-hidden
              className={cn(
                "size-3 shrink-0 text-text-subtle opacity-0 transition-transform group-hover:opacity-100",
                expanded && "rotate-90 opacity-100",
              )}
            />
          </span>
        </td>
        <td className="py-2 pr-3">
          {row.description ? (
            <TruncatedText text={row.description} className="text-xs text-text-muted" />
          ) : null}
        </td>
        <td className="py-2 pr-2 text-right tabular-nums">{uses}</td>
      </tr>
      {expanded ? (
        <tr className="border-b border-border-subtle">
          <td colSpan={COLUMNS} className="p-0">
            {row.resource ? (
              <McpResourceDetail serverUid={serverUid} resource={row.resource} />
            ) : row.prompt ? (
              <McpPromptDetail serverUid={serverUid} prompt={row.prompt} />
            ) : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}
