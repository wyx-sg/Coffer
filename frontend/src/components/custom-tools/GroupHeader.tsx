// src/components/custom-tools/GroupHeader.tsx — a group's header: name and health, where its tools come
// from, the last 24 hours in one line, Edit group and the ⋯ menu (Delete group… — Re-import is in the
// Definition section and on/off is its reach control, so the menu does not repeat them).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Pencil, Wrench } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { healthTone } from "@/lib/customTools/groups";

interface Props {
  group: CustomToolGroup;
  onEdit: () => void;
  onDelete: () => void;
}

export function GroupHeader({ group, onEdit, onDelete }: Props) {
  const { t } = useTranslation();
  const actions: MenuAction[] = [
    {
      key: "delete",
      label: t("customTools.group.deleteMenu"),
      destructive: true,
      separated: true,
      onSelect: onDelete,
    },
  ];

  return (
    <header className="flex items-start justify-between gap-4">
      <div className="flex min-w-0 gap-3">
        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
          <Wrench className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-xl font-bold">{group.name}</h1>
            <StatusPill tone={healthTone(group.health)}>
              {t(`customTools.health.${group.health}`)}
            </StatusPill>
            <HelpTip>
              <p className="text-xs text-text-muted">{t("customTools.group.help")}</p>
            </HelpTip>
          </div>
          <p className="text-sm text-text-muted">
            {group.source ? t("customTools.group.imported") : t("customTools.group.byHand")}
          </p>
          <p className="text-xs text-text-muted">
            {t("customTools.group.calls", { count: group.calls_24h })}
            {" · "}
            <span className={group.failures_24h > 0 ? "text-danger" : undefined}>
              {t("customTools.group.errors", { count: group.failures_24h })}
            </span>
            {` ${t("customTools.group.in24h")} · `}
            <Link to="/activity?tab=mcp" className="font-label text-accent-text hover:underline">
              {t("customTools.group.openActivity")}
            </Link>
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button variant="outline" onClick={onEdit}>
          <Pencil aria-hidden />
          {t("customTools.group.edit")}
        </Button>
        <ActionMenu label={t("customTools.group.more", { name: group.name })} actions={actions} />
      </div>
    </header>
  );
}
