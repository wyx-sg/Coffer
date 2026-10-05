// src/components/clis/CliHeader.tsx — the open command's header (board CliHeader): a state tile, the name with its status pill, one meta line, the description, and Edit (· ⋯ for a tool the person added).
//
// The meta line is "<title> · needed by 2 skills" or "<title> · added by you"
// (the title is the command's display name, left out when there is none);
// under it the description, and nothing when there is none. Edit
// opens the dialog for any command; only a tool the person added has ⋯ › Remove.
import { CircleAlert, Terminal, TriangleAlert, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { StatusPill } from "@/components/status/StatusPill";
import type { Cli } from "@/lib/api/clis";
import { cliTone, neededByCount, neededTotal } from "@/lib/clis/format";
import { cn } from "@/lib/utils";
import { CliActions } from "./CliActions";

const TILE: Record<Cli["status"], { icon: LucideIcon; className: string }> = {
  missing: { icon: CircleAlert, className: "bg-danger-soft text-danger" },
  outdated: { icon: TriangleAlert, className: "bg-warning-soft text-warning" },
  logged_out: { icon: TriangleAlert, className: "bg-warning-soft text-warning" },
  ready: {
    icon: Terminal,
    className: "border border-border-subtle bg-surface-sunken text-text-muted",
  },
};

export function CliHeader({ cli, onRemoved }: { cli: Cli; onRemoved: () => void }) {
  const { t } = useTranslation();
  const needed = neededTotal(cli);
  const meta = [
    cli.title,
    needed === 0
      ? t("clis.detail.addedByYou")
      : t("clis.detail.neededBy", { needed: neededByCount(t, cli) }),
  ]
    .filter(Boolean)
    .join(" · ");
  const tile = TILE[cli.status];
  const Icon = tile.icon;
  return (
    <header className="flex min-w-0 items-start gap-3">
      <span
        className={cn(
          "mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-lg",
          tile.className,
        )}
        data-testid="cli-tile"
        data-status={cli.status}
      >
        <Icon className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="min-w-0 truncate font-mono text-lg font-semibold text-text">
            {cli.command}
          </h2>
          <StatusPill tone={cliTone(cli.status)}>{t(`clis.status.${cli.status}`)}</StatusPill>
        </div>
        <p className="min-w-0 truncate text-xs text-text-muted first-letter:uppercase">{meta}</p>
        {cli.description ? (
          <p className="min-w-0 break-words text-xs text-text-muted" data-testid="cli-description">
            {cli.description}
          </p>
        ) : null}
      </div>
      <span className="inline-flex shrink-0 items-center gap-2 pt-0.5">
        <CliActions cli={cli} onRemoved={onRemoved} />
      </span>
    </header>
  );
}
