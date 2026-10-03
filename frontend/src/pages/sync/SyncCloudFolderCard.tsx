// frontend/src/pages/sync/SyncCloudFolderCard.tsx — 6.4.18: the vault sits in
// a folder another tool also syncs, so rounds are paused until it moves.
// "Move the vault…" opens the move dialog (6.4.19); Reveal in Finder shows the
// folder for a person who would rather move it themselves.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Cloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { translateApiError } from "@/lib/api/errors";
import type { SyncStatus } from "@/lib/api/sync";
import { SyncBannerCard } from "./SyncBanner";
import { SyncMoveVaultDialog } from "./SyncMoveVaultDialog";
import { Actions, Body } from "./SyncProblemParts";

export function SyncCloudFolderCard({
  status,
  onIgnore,
}: {
  status: SyncStatus;
  onIgnore?: () => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const [moving, setMoving] = useState(false);
  // `vault_path` may be a link to the folder; the real one is what the other tool syncs.
  const path = status.vault_real_path ?? status.vault_path;
  const tool = status.synchroniser ?? t("sync.problem.cloud_folder.someTool");
  return (
    <SyncBannerCard
      icon={Cloud}
      tone="warn"
      title={t("sync.problem.cloud_folder.title", { tool })}
      onIgnore={onIgnore}
      testId="sync-problem"
    >
      <Body>
        <span className="font-mono text-xs text-text">{path}</span>{" "}
        {t("sync.problem.cloud_folder.body", { tool })}
      </Body>
      <Actions>
        <Button type="button" variant="outline" size="sm" onClick={() => setMoving(true)}>
          {t("sync.problem.cloud_folder.move")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() =>
            void fs.reveal(path).catch((error: unknown) => toast.error(translateApiError(t, error)))
          }
        >
          {t("sync.problem.reveal")}
        </Button>
      </Actions>
      <SyncMoveVaultDialog open={moving} onOpenChange={setMoving} status={status} />
    </SyncBannerCard>
  );
}
