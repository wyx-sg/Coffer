// src/components/mcp/server/McpServerHeader.tsx — the open server's header in the MCP servers page's pane (design 4.1.02).
//
// An icon tile tinted by the state, the fixed name in mono with the state
// pill, one truncated line `transport · command or URL`; and the actions in
// the one detail order — reach, then the state's own next step (Test, Test
// again, Turn on, Replace secret), Edit, and the "⋯" menu: Edit… · Calls and
// server log · Copy config as JSON · Turn off / Turn on · Delete….
import { useTranslation } from "react-i18next";
import {
  CircleAlert,
  KeyRound,
  Pencil,
  Play,
  Power,
  RefreshCw,
  Server,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { ResourceOut } from "@/lib/api/resources";
import { cn } from "@/lib/utils";
import type { ServerState } from "./serverState";
import { transportOf } from "./serverState";

/** The tile's glyph and tint per state (design 4.1.01–4.1.05). */
function tileOf(kind: ServerState["kind"]): { icon: LucideIcon; className: string } {
  if (kind === "failing") return { icon: CircleAlert, className: "bg-danger-soft text-danger" };
  if (kind === "launcherMissing")
    return { icon: TriangleAlert, className: "bg-warning-soft text-warning" };
  if (kind === "secretMissing")
    return { icon: KeyRound, className: "bg-warning-soft text-warning" };
  return {
    icon: Server,
    className: "border border-border-subtle bg-surface-sunken text-text-muted",
  };
}

interface Props {
  resource: ResourceOut;
  state: ServerState;
  testing: boolean;
  onTest: () => void;
  onEdit: (focus?: "secret") => void;
  onOpenLog: () => void;
  onCopyConfig: () => void;
  onTurn: (on: boolean) => void;
  onDelete: () => void;
}

export function McpServerHeader({
  resource,
  state,
  testing,
  onTest,
  onEdit,
  onOpenLog,
  onCopyConfig,
  onTurn,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const transport = transportOf(resource.config);
  const off = state.kind === "off";

  let primary: JSX.Element;
  if (off) {
    primary = (
      <Button size="sm" variant="outline" onClick={() => onTurn(true)}>
        <Power aria-hidden /> {t("mcp.page.turnOn")}
      </Button>
    );
  } else if (state.kind === "secretMissing") {
    primary = (
      <Button size="sm" variant="outline" onClick={() => onEdit("secret")}>
        <KeyRound aria-hidden /> {t("mcp.page.replaceSecret")}
      </Button>
    );
  } else {
    const again = state.kind === "failing" || state.kind === "launcherMissing";
    primary = (
      <Button size="sm" variant="outline" onClick={onTest} disabled={testing}>
        {again ? <RefreshCw aria-hidden /> : <Play aria-hidden />}
        {testing ? t("mcp.page.testing") : again ? t("mcp.page.testAgain") : t("mcp.page.test")}
      </Button>
    );
  }

  const actions: MenuAction[] = [
    { key: "edit", label: t("mcp.page.menu.edit"), onSelect: () => onEdit() },
    { key: "log", label: t("mcp.page.menu.log"), onSelect: onOpenLog },
    { key: "copy", label: t("mcp.page.menu.copyConfig"), onSelect: onCopyConfig },
    off
      ? { key: "on", label: t("mcp.page.turnOn"), onSelect: () => onTurn(true) }
      : { key: "off", label: t("mcp.page.menu.turnOff"), onSelect: () => onTurn(false) },
    {
      key: "delete",
      label: t("mcp.page.menu.delete"),
      onSelect: onDelete,
      destructive: true,
      separated: true,
    },
  ];

  const tile = tileOf(state.kind);
  const Icon = tile.icon;
  return (
    <header className="flex min-w-0 items-center gap-3">
      <span
        className={cn(
          "inline-flex size-9 shrink-0 items-center justify-center rounded-lg",
          tile.className,
        )}
        data-testid="mcp-server-tile"
        data-state={state.kind}
      >
        <Icon className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2">
          {/* Its title when set, its fixed name (mono) otherwise. */}
          <h1
            className={cn(
              "min-w-0 truncate text-lg font-semibold",
              resource.title ? "" : "font-mono",
            )}
          >
            {resource.title || resource.name}
          </h1>
          <StatusPill tone={state.tone}>{t(`mcp.page.state.${state.kind}`)}</StatusPill>
        </div>
        <p
          className="min-w-0 truncate text-xs text-text-muted"
          data-testid="mcp-server-target"
          data-visual-volatile
        >
          {t(`mcp.page.transport.${transport.type}`)}
          {transport.target ? (
            <>
              <span aria-hidden className="text-text-subtle">
                {" · "}
              </span>
              <span className="font-mono">{transport.target}</span>
            </>
          ) : null}
        </p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        <ScopeControl
          kind="mcp_server"
          uid={resource.uid}
          enabled={resource.enabled}
          scope={resource.scope ?? null}
        />
        {primary}
        <Button size="sm" variant="outline" onClick={() => onEdit()}>
          <Pencil aria-hidden /> {t("mcp.page.edit")}
        </Button>
        <ActionMenu label={t("mcp.page.menu.label", { name: resource.name })} actions={actions} />
      </span>
    </header>
  );
}
