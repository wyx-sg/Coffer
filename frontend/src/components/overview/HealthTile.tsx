// src/components/overview/HealthTile.tsx — one area's quiet one-line summary on the Overview, opening its page.
//
// Three rows: the area and its status word; a big number and its unit; one
// muted line of detail. Each tile loads and fails on its own — a failed one
// says so, with Retry and a way to its page, while the rest keep working
// (design board "One area failed to load").
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { StatusWord } from "@/components/status/StatusWord";
import type { StatusTone } from "@/components/status/statusTone";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

/** @ui-only What a tile shows once its list has loaded. */
export interface TileContent {
  /** The status word, or null while the attention list has not answered. */
  status: { tone: StatusTone; text: string } | null;
  value: ReactNode;
  unit?: string;
  summary?: ReactNode;
}

interface Props {
  to: string;
  label: string;
  icon: LucideIcon;
  state:
    | { kind: "loading" }
    | { kind: "error"; error: unknown; retry: () => void }
    | { kind: "ready"; content: TileContent };
}

const TILE =
  "flex min-h-28 flex-col gap-1.5 rounded-xl border border-border-subtle bg-surface-raised px-4 py-3.5";

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
    <div className="flex items-center gap-2">
      <Icon className="size-4 shrink-0 text-text-subtle" strokeWidth={1.75} aria-hidden />
      <span className="truncate text-sm font-semibold text-text">{label}</span>
      <span className="ml-auto">{status}</span>
    </div>
  );
}

export function HealthTile({ to, label, icon, state }: Props) {
  const { t } = useTranslation();

  if (state.kind === "error") {
    // Not a link: it holds two actions of its own.
    return (
      <div className={TILE} role="group" aria-label={label}>
        <TileHead
          icon={icon}
          label={label}
          status={<StatusWord tone="err">{t("overview.health.loadFailed")}</StatusWord>}
        />
        <p className="truncate text-xs text-text-muted">{translateApiError(t, state.error)}</p>
        <div className="mt-auto flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={state.retry}>
            {t("overview.retry")}
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link to={to}>{t("overview.health.open", { area: label })}</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <Link
      to={to}
      aria-label={label}
      className={cn(TILE, "transition-colors duration-fast hover:bg-surface-hover")}
    >
      {state.kind === "loading" ? (
        <>
          <TileHead icon={icon} label={label} />
          <Skeleton className="h-6 w-20" />
          <Skeleton className="h-3 w-32" />
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
              ) : null
            }
          />
          <p className="flex items-baseline gap-1.5">
            <span className="text-xl font-bold text-text">{state.content.value}</span>
            {state.content.unit ? (
              <span className="text-xs text-text-muted">{state.content.unit}</span>
            ) : null}
          </p>
          {state.content.summary ? (
            <div className="truncate text-xs text-text-muted">{state.content.summary}</div>
          ) : null}
        </>
      )}
    </Link>
  );
}
