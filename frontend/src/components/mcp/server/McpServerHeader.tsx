// src/components/mcp/server/McpServerHeader.tsx — the open server's header in the MCP servers page's pane (design 4.1.02).
//
// An icon tile tinted by the state, the fixed name in mono with the state
// pill, one truncated line `transport · command or URL`; and the actions, fixed
// whatever the state — Reach · Test · Edit · "⋯" (Server log, stdio only · Copy
// config as JSON · Turn off · Delete…). A problem's fix lives in the Overview's
// banner, never here.
import { useTranslation } from "react-i18next";
import {
  CircleAlert,
  KeyRound,
  Pencil,
  Play,
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
import type { ServerState } from "@/lib/mcp/serverState";
import { transportOf } from "@/lib/mcp/serverState";

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
  onEdit: () => void;
  onOpenLog: () => void;
  onCopyConfig: () => void;
  onTurnOff: () => void;
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
  onTurnOff,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const transport = transportOf(resource.config);

  const actions: MenuAction[] = [
    // A Streamable HTTP server runs somewhere else: Coffer keeps no log for it.
    ...(transport.type === "http"
      ? []
      : [{ key: "log", label: t("mcp.page.menu.log"), onSelect: onOpenLog }]),
    { key: "copy", label: t("mcp.page.menu.copyConfig"), onSelect: onCopyConfig },
    ...(state.kind === "off"
      ? []
      : [{ key: "off", label: t("mcp.page.menu.turnOff"), onSelect: onTurnOff }]),
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
          {/* A server carries no title: its fixed name, in mono. */}
          <h1 className="min-w-0 truncate font-mono text-lg font-semibold">{resource.name}</h1>
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
        <Button size="sm" variant="outline" onClick={onTest} disabled={testing}>
          <Play aria-hidden /> {testing ? t("mcp.page.testing") : t("mcp.page.test")}
        </Button>
        <Button size="sm" variant="outline" onClick={onEdit}>
          <Pencil aria-hidden /> {t("mcp.page.edit")}
        </Button>
        <ActionMenu label={t("mcp.page.menu.label", { name: resource.name })} actions={actions} />
      </span>
    </header>
  );
}
