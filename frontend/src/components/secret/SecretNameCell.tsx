// src/components/secret/SecretNameCell.tsx — the Name cell: the secret's own short name and what needs attention.
//
// The name is the ref's last segment in mono (the full ref, a standalone secret's URI, is its
// tooltip when it is clipped). Beside it, a status word: "No value on this Mac" (danger) for a
// ref this Mac cannot hand out, "Waiting for approval" (warning) while a new value or destination
// waits; and a mark for a value other local processes can read. The checkbox is its own column.
import { TerminalSquare } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { TruncatedText } from "@/components/ui/truncated-text";
import { referenceOf } from "./secretRows";
import type { SecretItem } from "./secretListView";

export function SecretNameCell({ item }: { item: SecretItem }) {
  const { t } = useTranslation();
  const { row } = item;
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <div className="min-w-0">
        <TruncatedText text={referenceOf(row)} mono className="text-xs text-text">
          {item.short}
        </TruncatedText>
      </div>
      {item.missing ? <StatusWord tone="err">{t("secrets.row.missing")}</StatusWord> : null}
      {item.pending ? <StatusWord tone="warn">{t("secrets.row.pending")}</StatusWord> : null}
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
          <TooltipContent>{t("secrets.row.localReadable")}</TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}
