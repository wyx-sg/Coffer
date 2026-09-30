// src/components/custom-tools/GroupHeader.tsx — a group's header: name and health, where its tools come
// from, the last 24 hours in one line, and the actions (switch → edit → delete).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Pencil, Trash2 } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { healthTone } from "@/lib/customTools/groups";
import { useDisableResource, useEnableResource } from "@/lib/hooks/useResourceMutations";

interface Props {
  group: CustomToolGroup;
  onEdit: () => void;
  onDelete: () => void;
}

export function GroupHeader({ group, onEdit, onDelete }: Props) {
  const { t } = useTranslation();
  const enable = useEnableResource();
  const disable = useDisableResource();
  const busy = enable.isPending || disable.isPending;
  const title = group.source?.title || group.name;

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-bold tracking-[-0.01em]">{title}</h1>
          <StatusPill tone={healthTone(group.health)}>
            {t(`customTools.health.${group.health}`)}
          </StatusPill>
          <HelpTip>
            <p className="text-xs text-text-muted">{t("customTools.group.help")}</p>
          </HelpTip>
        </div>
        <p className="text-sm text-text-muted">
          <span className="font-mono">{group.name}</span>
          {" · "}
          {group.source ? t("customTools.group.imported") : t("customTools.group.byHand")}
        </p>
        <p className="text-xs text-text-muted">
          {t("customTools.group.calls", { count: group.calls_24h })}
          {" · "}
          <span className={group.failures_24h > 0 ? "text-danger" : undefined}>
            {t("customTools.group.errors", { count: group.failures_24h })}
          </span>
          {` ${t("customTools.group.in24h")} · `}
          <Link to="/activity?tab=mcp" className="text-accent-text hover:underline">
            {t("customTools.group.openActivity")}
          </Link>
        </p>
      </div>
      <div className="flex items-center gap-2">
        <label className="mr-1 inline-flex items-center gap-2 text-xs text-text-muted">
          <Switch
            checked={group.enabled}
            disabled={busy}
            aria-label={t("customTools.group.enabled", { name: group.name })}
            onCheckedChange={(on) =>
              (on ? enable : disable).mutate({ kind: "mcp_server", uid: group.uid })
            }
          />
          {group.enabled ? t("customTools.tools.on") : t("customTools.tools.off")}
        </label>
        <Button variant="outline" onClick={onEdit}>
          <Pencil aria-hidden />
          {t("customTools.group.edit")}
        </Button>
        <Button variant="danger" onClick={onDelete}>
          <Trash2 aria-hidden />
          {t("customTools.group.delete")}
        </Button>
      </div>
    </header>
  );
}
