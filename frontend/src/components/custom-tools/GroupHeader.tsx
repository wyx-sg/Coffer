// src/components/custom-tools/GroupHeader.tsx — a group's header (4.2.01 · CtGroupHeader): an icon tile tinted by
// the state, the fixed name in mono with the state pill, one 12px meta line (where its tools came from · the last
// 24 hours), and the actions, fixed whatever the state — Reach · Edit group · ⋯ (Delete group…). A problem's fix
// lives in the banner under the header, never here.
import { useTranslation } from "react-i18next";
import { CircleAlert, KeyRound, Pencil, Wrench, type LucideIcon } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { groupScope, groupState, healthTone, type GroupState } from "@/lib/customTools/groups";
import { cn } from "@/lib/utils";

interface Props {
  group: CustomToolGroup;
  onEdit: () => void;
  onDelete: () => void;
}

/** The tile's glyph and tint per state (4.2.01–4.2.23). */
function tileOf(state: GroupState): { icon: LucideIcon; className: string } {
  if (state === "failing") return { icon: CircleAlert, className: "bg-danger-soft text-danger" };
  if (state === "secretMissing" || state === "waiting" || state === "refused")
    return { icon: KeyRound, className: "bg-warning-soft text-warning" };
  return {
    icon: Wrench,
    className: "border border-border-subtle bg-surface-sunken text-text-muted",
  };
}

/** The meta line's last part: the last 24 hours in words. */
function useCallsLine(group: CustomToolGroup): string {
  const { t } = useTranslation();
  if (group.calls_24h === 0)
    return t(group.enabled ? "customTools.group.noCalls" : "customTools.group.noCallsOff");
  return t("customTools.group.callsLine", {
    calls: t("customTools.group.calls", { count: group.calls_24h }),
    errors: t("customTools.group.errors", { count: group.failures_24h }),
  });
}

export function GroupHeader({ group, onEdit, onDelete }: Props) {
  const { t } = useTranslation();
  const state = groupState(group);
  const tile = tileOf(state);
  const Icon = tile.icon;
  const calls = useCallsLine(group);
  const source = group.source;
  const spec = source ? [source.title, source.version].filter(Boolean).join(" ") : "";
  const actions: MenuAction[] = [
    {
      key: "delete",
      label: t("customTools.group.deleteMenu"),
      destructive: true,
      onSelect: onDelete,
    },
  ];

  return (
    <header className="flex min-w-0 items-center gap-3">
      <span
        className={cn(
          "inline-flex size-9 shrink-0 items-center justify-center rounded-lg",
          tile.className,
        )}
        data-testid="custom-tool-group-tile"
        data-state={state}
      >
        <Icon className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <h1 className="min-w-0 truncate font-mono text-lg font-semibold">{group.name}</h1>
          <StatusPill tone={healthTone(group.health)}>{t(`customTools.state.${state}`)}</StatusPill>
        </div>
        <p className="min-w-0 truncate text-xs text-text-muted">
          {source ? t("customTools.group.imported") : t("customTools.group.byHand")}
          {spec ? (
            <>
              <span className="text-text-subtle"> · </span>
              {spec}
            </>
          ) : null}
          <span className="text-text-subtle"> · </span>
          {calls}
        </p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        <ScopeControl
          kind="mcp_server"
          uid={group.uid}
          enabled={group.enabled}
          scope={groupScope(group)}
          resourceName={group.name}
        />
        <Button variant="outline" onClick={onEdit}>
          <Pencil aria-hidden />
          {t("customTools.group.edit")}
        </Button>
        <ActionMenu label={t("customTools.group.more", { name: group.name })} actions={actions} />
      </span>
    </header>
  );
}
