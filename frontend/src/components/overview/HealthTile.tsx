// src/components/overview/HealthTile.tsx — one area's quiet one-line summary on the Overview, opening its page.
//
// Three rows in a 112-high card: the area and its status word; a big number
// and its unit; one muted line of detail. Each tile loads and fails on its
// own — a failed one says what failed, the failed request in mono (method,
// path, area, status, trace), Retry and a link to its page, while the rest
// keep working (Overview board 1.2.04 "Partial failure").
import { RotateCcw, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { StatusWord } from "@/components/status/StatusWord";
import type { StatusTone } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TruncatedText } from "@/components/ui/truncated-text";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/** @ui-only What a tile shows once its list has loaded. */
export interface TileContent {
  /** The status word, or null while the attention list has not answered. */
  status: { tone: StatusTone; text: string } | null;
  /** Plain meta in the status word's place, for an area with no health of
   *  its own (Usage reads "Today"). Ignored when `status` is set. */
  note?: string;
  value: ReactNode;
  unit?: string;
  summary?: ReactNode;
}

interface Props {
  to: string;
  label: string;
  /** The area's name in the failed-request line ("knowledge", "mcp-servers"). */
  area: string;
  icon: LucideIcon;
  state:
    | { kind: "loading" }
    | { kind: "error"; error: unknown; retry: () => void }
    | { kind: "ready"; content: TileContent };
}

const TILE =
  "flex h-28 min-w-0 flex-col gap-2 rounded-xl border border-border bg-surface-raised px-4 py-3.5";

function TileHead({
  icon: Icon,
  label,
  status,
}: {
  icon: LucideIcon;
  label: string;
  status?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <Icon className="size-[15px] shrink-0 text-text-subtle" strokeWidth={1.75} aria-hidden />
      <span className="truncate text-sm font-semibold text-text">{label}</span>
      <span className="ml-auto">{status}</span>
    </div>
  );
}

/** "GET /api/v1/overview · knowledge · 503 · trace 01JA2M7X4Q": the failed request, with the area
 *  after its path; empty when the error never reached the daemon. */
function failedRequest(error: unknown, area: string): string {
  const r = error instanceof ApiError ? error.request : undefined;
  if (!r) return "";
  return [
    r.path ? `GET ${r.path}` : null,
    area,
    r.status !== undefined ? String(r.status) : null,
    r.trace ? `trace ${r.trace}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function HealthTile({ to, label, area, icon, state }: Props) {
  const { t } = useTranslation();

  if (state.kind === "error") {
    // Not a link: it holds two actions of its own.
    const failed = failedRequest(state.error, area);
    return (
      <div
        className={TILE}
        role="group"
        aria-label={t("overview.health.loadFailedLabel", { area: label })}
      >
        <TileHead
          icon={icon}
          label={label}
          status={<StatusWord tone="err">{t("overview.health.loadFailed")}</StatusWord>}
        />
        <div className="flex min-w-0 flex-col gap-[3px]">
          <p className="truncate text-sm text-text">{translateApiError(t, state.error)}</p>
          {failed ? <p className="truncate font-mono text-2xs text-text-subtle">{failed}</p> : null}
        </div>
        <div className="mt-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={state.retry}>
            <RotateCcw aria-hidden />
            {t("overview.retry")}
          </Button>
          <Link
            to={to}
            className="rounded-xs text-xs font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            {t("overview.health.open", { area: label })}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <Link
      to={to}
      aria-label={label}
      className={cn(
        TILE,
        "transition-colors duration-fast hover:bg-surface-hover",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
      )}
    >
      {state.kind === "loading" ? (
        <>
          <TileHead icon={icon} label={label} />
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-2.5 w-32" />
        </>
      ) : (
        <>
          <TileHead
            icon={icon}
            label={label}
            status={
              state.content.status ? (
                <StatusWord tone={state.content.status.tone}>
                  {state.content.status.text}
                </StatusWord>
              ) : state.content.note ? (
                <span className="whitespace-nowrap text-xs text-text-subtle">
                  {state.content.note}
                </span>
              ) : null
            }
          />
          <p className="flex min-w-0 items-baseline gap-1.5">
            <span className="whitespace-nowrap text-xl font-bold text-text">
              {state.content.value}
            </span>
            {state.content.unit ? (
              <span className="truncate text-sm text-text-muted">{state.content.unit}</span>
            ) : null}
          </p>
          {typeof state.content.summary === "string" && state.content.summary ? (
            <TruncatedText text={state.content.summary} className="text-xs text-text-muted" />
          ) : state.content.summary ? (
            <div className="truncate text-xs text-text-muted">{state.content.summary}</div>
          ) : null}
        </>
      )}
    </Link>
  );
}
