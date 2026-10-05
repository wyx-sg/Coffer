// frontend/src/components/agents/AgentConfigFilePreviewDialog.tsx
// One config file of an agent, read-only, in a dialog — spec agent-registry
// "Preview an agent's config file read-only".
// Reached from a file's name on the Config files tab. The body is the shared
// read-only viewer; the file is shown as it is on disk. Changing the file is
// what the viewer's Open in editor is for, so there is no Edit or Save here.
import { useTranslation } from "react-i18next";

import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { abbreviateHomePath } from "@/lib/agents/display";
import { useAgentConfigFileContent } from "@/lib/hooks/useAgents";

/** The file a row opened: its allowlist key, the child relpath under a directory entry, its name. */
export interface ConfigFileTarget {
  key: string;
  child?: string;
  name: string;
  /** The absolute path, shown until the read answers. */
  path: string;
}

export function AgentConfigFilePreviewDialog({
  agentUid,
  target,
  onClose,
}: {
  agentUid: string;
  /** The row opened; null keeps the dialog closed. */
  target: ConfigFileTarget | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const query = useAgentConfigFileContent(agentUid, target?.key ?? "", target?.child ?? "");
  return (
    <Dialog open={target !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-[880px]">
        <DialogHeader>
          <DialogTitle className="font-mono">{target?.name}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("agents.config.preview.description")}
          </DialogDescription>
        </DialogHeader>

        <div className="flex h-[60vh] min-h-0 flex-col overflow-hidden rounded-lg border border-border-subtle">
          {target ? (
            <ReadOnlyFile
              path={target.name}
              displayPath={abbreviateHomePath(query.data?.abs_path ?? target.path)}
              query={query}
              reveal
            />
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
