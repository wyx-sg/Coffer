// src/components/agents/list/ConfigLeftBehindNotice.tsx — the warning under a config-left-behind row.
//
// The directory is still on disk but the program is gone, so nothing Coffer
// writes can reach it; reinstalling brings the row back on its own (detection
// re-reads it). Offers the daemon's reinstall prompt (Copy prompt, and Ask an
// agent while another managed agent is available), the folder, and — for an
// agent still added — taking it out of the list.
import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { AlertTriangle, FolderOpen, Trash2 } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Alert } from "@/components/ui/alert";
import { TableActionButton } from "@/components/table/TableActionButton";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath, agentProgramName } from "@/lib/agents/display";
import type { AgentTypeOut } from "@/lib/api/agents";
import { useFsActions } from "@/lib/fsActions";
import { AgentRemoveDialog } from "./AgentRemoveDialog";

export function ConfigLeftBehindNotice({ row }: { row: AgentTypeOut }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const [removeOpen, setRemoveOpen] = useState(false);
  return (
    <Alert variant="warning" className="flex items-center gap-3">
      <AlertTriangle aria-hidden />
      <p className="min-w-0 grow leading-[1.45]">
        <Trans
          i18nKey="agents.list.leftBehind.body"
          values={{
            dir: abbreviateHomePath(row.config_dir),
            program: agentProgramName(row.type),
          }}
          components={{ code: <span className="break-all font-mono text-text" /> }}
        />
      </p>
      <span className="flex shrink-0 gap-2 !pl-0" onClick={(event) => event.stopPropagation()}>
        {row.install_handoff ? (
          <AgentHandoff prompt={row.install_handoff.prompt} size="sm" />
        ) : null}
        <TableActionButton
          icon={FolderOpen}
          label={t("agents.list.leftBehind.reveal")}
          onClick={() =>
            void fs
              .reveal(row.config_dir)
              .catch(() => toast.error(t("agents.rowMenu.revealFailed")))
          }
        />
        {row.uid ? (
          <TableActionButton
            icon={Trash2}
            label={t("agents.list.leftBehind.remove")}
            onClick={() => setRemoveOpen(true)}
          />
        ) : null}
        {row.uid ? (
          <AgentRemoveDialog row={row} open={removeOpen} onOpenChange={setRemoveOpen} />
        ) : null}
      </span>
    </Alert>
  );
}
