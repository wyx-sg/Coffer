// src/components/agents/AgentHookRowActions.tsx — a Hooks-tab row's actions: Open file, and Repair on Coffer's hook.
//
// Hooks are changed in their own files, so a row opens the file that declares it
// in the user's editor (lib/fileActionItems, which toasts a failure). Coffer's
// own hook, when out of date or missing, also offers Repair — reinstalling it
// through the Coffer connection — when the tab is given a way to run it.
import { useTranslation } from "react-i18next";
import { ExternalLink, Wrench } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { cofferHookState, type HookRow } from "@/lib/agents/hookRows";
import { useFileActionItems } from "@/lib/fileActionItems";

interface Props {
  row: HookRow;
  onRepair?: () => void;
}

export function AgentHookRowActions({ row, onRepair }: Props) {
  const { t } = useTranslation();
  const open = useFileActionItems(row.path).find((item) => item.key === "open");
  const repair = row.coffer !== null && cofferHookState(row.coffer).repair;
  return (
    <span className="flex flex-wrap justify-end gap-2">
      {repair && onRepair ? (
        <TableActionButton icon={Wrench} label={t("agents.hooksTab.repair")} onClick={onRepair} />
      ) : null}
      {row.command !== null && open ? (
        <TableActionButton
          icon={ExternalLink}
          label={t("agents.hooksTab.openFile")}
          aria-label={t("agents.hooksTab.openFileAria", { path: row.path })}
          onClick={open.onClick}
        />
      ) : null}
    </span>
  );
}
