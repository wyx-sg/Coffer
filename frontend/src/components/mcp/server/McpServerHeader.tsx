// src/components/mcp/server/McpServerHeader.tsx — the open server's header in the MCP servers page's pane (design 4.1.02).
//
// Its title (the fixed name when there is none) with the state pill; the line
// `name · transport · command or URL`; and the actions in the one detail
// order — reach, then the state's own next step (Test, Test again, Turn on,
// Replace secret), Edit, and the "⋯" menu: Edit… · Calls and server log ·
// Copy config as JSON · Turn off / Turn on · Delete….
import { useTranslation } from "react-i18next";
import { Activity, KeyRound, Pencil, Power, Server } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { ResourceOut } from "@/lib/api/resources";
import type { ServerState } from "./serverState";
import { transportOf } from "./serverState";

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
        <Activity aria-hidden />
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

  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Server className="size-4" strokeWidth={1.75} aria-hidden />
        </span>
        <h1 className="min-w-0 truncate text-lg font-bold">{resource.title || resource.name}</h1>
        <StatusPill tone={state.tone}>{t(`mcp.page.state.${state.kind}`)}</StatusPill>
        <span className="ml-auto inline-flex flex-wrap items-center gap-2">
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
      </div>
      <p className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-text-muted">
        <span className="font-mono">{resource.name}</span>
        <span aria-hidden className="text-text-subtle">
          ·
        </span>
        <span>{t(`mcp.page.transport.${transport.type}`)}</span>
        {transport.target ? (
          <>
            <span aria-hidden className="text-text-subtle">
              ·
            </span>
            <span
              className="min-w-0 break-all font-mono"
              data-testid="mcp-server-target"
              data-visual-volatile
            >
              {transport.target}
            </span>
          </>
        ) : null}
      </p>
    </header>
  );
}
