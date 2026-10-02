// src/components/secret/SecretNameCell.tsx — the Name cell: the secret's own short name, who owns it in words, and what needs attention.
//
// The name is the ref's last segment in mono; the full ref (a standalone secret's URI) is its
// tooltip. Under it, one muted line names the owner ("MCP server · jira"). Beside the name:
// "Missing on this Mac" for a ref this Mac has no value for, "Waiting for approval" while a new
// value or destination waits, and a mark for a value other local processes can read. The
// leading icon turns into the row's checkbox on hover or focus, and stays one once any row is ticked.
import { KeyRound, TerminalSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { TruncatedText } from "@/components/ui/truncated-text";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { isMissingHere, referenceOf } from "./secretRows";
import type { SecretItem } from "./secretListView";
import { useOwnerLabel } from "./useOwnerLabel";

interface Props {
  item: SecretItem;
  /** Any row is ticked: every row shows its checkbox. */
  selecting: boolean;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  /** Leave the owner line out (the by-owner view already says it). */
  hideOwner?: boolean;
}

export function SecretNameCell({ item, selecting, checked, onCheckedChange, hideOwner }: Props) {
  const { t } = useTranslation();
  const { ownerLine } = useOwnerLabel();
  const { row } = item;
  const showBox = selecting || checked;
  const line = ownerLine(item.owner, row.ref, row.uri !== null);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span className="relative inline-flex size-[15px] shrink-0">
        <KeyRound
          aria-hidden
          className={cn(
            "absolute inset-0 m-auto size-3.5 text-text-muted",
            showBox ? "opacity-0" : "[tr:focus-within_&]:opacity-0 [tr:hover_&]:opacity-0",
          )}
        />
        <Checkbox
          className={cn(
            "absolute inset-0",
            showBox
              ? "opacity-100"
              : "opacity-0 focus-within:opacity-100 [tr:focus-within_&]:opacity-100 [tr:hover_&]:opacity-100",
          )}
          checked={checked}
          onChange={(e) => onCheckedChange(e.target.checked)}
          aria-label={t("secrets.row.select", { name: item.short })}
        />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="min-w-0 truncate font-mono text-xs text-text">{item.short}</span>
            </TooltipTrigger>
            <TooltipContent className="max-w-[420px] break-all">{referenceOf(row)}</TooltipContent>
          </Tooltip>
          {isMissingHere(row) ? (
            <Badge variant="destructive" className="shrink-0 rounded-full">
              {t("secrets.row.missing")}
            </Badge>
          ) : null}
          {item.pending ? (
            <Badge variant="warning" className="shrink-0 rounded-full">
              {t("secrets.row.pending")}
            </Badge>
          ) : null}
          {row.readable_by_local_processes ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  tabIndex={0}
                  aria-label={t("secrets.row.localReadable")}
                  className="inline-flex shrink-0 text-text-subtle"
                >
                  <TerminalSquare className="size-3.5" aria-hidden />
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-[260px]">
                {t("secrets.row.localReadableHint")}
              </TooltipContent>
            </Tooltip>
          ) : null}
        </div>
        {hideOwner ? null : <TruncatedText text={line} className="text-xs text-text-muted" />}
      </div>
    </div>
  );
}
