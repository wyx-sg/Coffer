// src/components/chat/DiffDrawer.tsx — one reply's diff of one changed file, in a
// 640 drawer on the right that starts under the title bar (Chat-DiffDrawer,
// 3.1.09). The header carries the path, its +/− counts, "n of N" with previous /
// next file and close; Esc closes too. Previous / next walk the reply's files
// that have a diff. The body is the unified diff: old and new line numbers, hunk
// headers, added and removed lines tinted. A file left out of the record says so.
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { LineCounts } from "@/components/change-preview/LineCounts";
import { Button } from "@/components/ui/button";
import { Sheet, SheetBody, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { TruncatedText } from "@/components/ui/truncated-text";
import { translateApiError } from "@/lib/api/errors";
import { parseUnifiedDiff, type DiffRow } from "@/lib/chat/unifiedDiff";
import { relativeToCwd } from "@/lib/conversations/filesChanged";
import { useAgentConfig, useReplyFileDiff, useReplyFiles } from "@/lib/hooks/useConversations";
import { cn } from "@/lib/utils";

interface Props {
  conversationId: string;
  messageId: string;
  /** The open file's path, as recorded (absolute). */
  path: string;
  onPathChange: (path: string) => void;
  onClose: () => void;
}

export function DiffDrawer({ conversationId, messageId, path, onPathChange, onClose }: Props) {
  const { t } = useTranslation();
  const files = useReplyFiles(conversationId, messageId);
  const { data: agentConfig } = useAgentConfig(conversationId);
  const walkable = useMemo(() => (files.data ?? []).filter((f) => f.has_diff), [files.data]);
  const index = walkable.findIndex((f) => f.path === path);
  const current = index >= 0 ? walkable[index] : null;
  const go = (to: number) => {
    const next = walkable[to];
    if (next) onPathChange(next.path);
  };
  const shown = relativeToCwd(path, agentConfig?.cwd ?? null);

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent showClose={false} aria-describedby={undefined}>
        <TooltipProvider>
          <div className="flex h-[52px] shrink-0 items-center gap-2.5 border-b border-border-subtle pl-5 pr-3">
            <SheetTitle className="min-w-0 text-sm font-semibold">
              <TruncatedText text={path} mono>
                {shown}
              </TruncatedText>
            </SheetTitle>
            <LineCounts added={current?.added} removed={current?.removed} className="text-xs" />
            <span className="ml-auto flex shrink-0 items-center gap-0.5">
              {index >= 0 ? (
                <span className="mr-1 text-xs text-text-subtle">
                  {t("conversations.diff.position", { n: index + 1, total: walkable.length })}
                </span>
              ) : null}
              <IconButton
                label={t("conversations.diff.previous")}
                disabled={index <= 0}
                onClick={() => go(index - 1)}
              >
                <ChevronLeft className="size-4" aria-hidden />
              </IconButton>
              <IconButton
                label={t("conversations.diff.next")}
                disabled={index < 0 || index >= walkable.length - 1}
                onClick={() => go(index + 1)}
              >
                <ChevronRight className="size-4" aria-hidden />
              </IconButton>
              <span className="mx-1 h-4 w-px bg-border" aria-hidden />
              <IconButton label={t("common.close")} onClick={onClose}>
                <X className="size-4" aria-hidden />
              </IconButton>
            </span>
          </div>
        </TooltipProvider>
        <SheetBody className="px-0 py-3">
          <DiffBody conversationId={conversationId} messageId={messageId} path={path} />
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function DiffBody({
  conversationId,
  messageId,
  path,
}: {
  conversationId: string;
  messageId: string;
  path: string;
}) {
  const { t } = useTranslation();
  const query = useReplyFileDiff(conversationId, messageId, path);
  const hunks = useMemo(
    () => (query.data?.diff ? parseUnifiedDiff(query.data.diff) : []),
    [query.data?.diff],
  );
  if (query.isPending) {
    return (
      <div className="mx-4 space-y-1.5" aria-busy="true" aria-label={t("common.loading")}>
        {Array.from({ length: 10 }, (_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
    );
  }
  if (query.error) {
    return (
      <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
        <p className="text-sm text-danger">{translateApiError(t, query.error)}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void query.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }
  const omitted = query.data.diff_omitted;
  if (omitted || hunks.length === 0) {
    return (
      <p className="px-6 py-12 text-center text-sm text-text-muted">
        {omitted === "too_large"
          ? t("conversations.diff.tooLarge")
          : omitted === "binary"
            ? t("conversations.diff.binary")
            : t("conversations.diff.empty")}
      </p>
    );
  }
  return (
    <div className="mx-4 overflow-hidden rounded-lg border border-border">
      {hunks.map((hunk, i) => (
        <div key={i}>
          <div className="bg-surface-sunken px-3 py-1 font-mono text-xs leading-5 text-text-subtle">
            {hunk.header}
          </div>
          {hunk.rows.map((row, j) => (
            <Row key={j} row={row} />
          ))}
        </div>
      ))}
    </div>
  );
}

const MARK: Record<DiffRow["kind"], string> = { context: "", add: "+", del: "-" };

function Row({ row }: { row: DiffRow }) {
  return (
    <div
      className={cn(
        "flex font-mono text-xs leading-5",
        row.kind === "add" && "bg-success-soft",
        row.kind === "del" && "bg-danger-soft",
      )}
    >
      <span className="w-10 shrink-0 select-none pr-2 text-right text-text-subtle">
        {row.oldNo}
      </span>
      <span className="w-10 shrink-0 select-none pr-2 text-right text-text-subtle">
        {row.newNo}
      </span>
      <span
        className={cn(
          "w-4 shrink-0 select-none",
          row.kind === "add" && "text-success",
          row.kind === "del" && "text-danger",
        )}
      >
        {MARK[row.kind]}
      </span>
      <span className="whitespace-pre text-text">{row.text}</span>
    </div>
  );
}
