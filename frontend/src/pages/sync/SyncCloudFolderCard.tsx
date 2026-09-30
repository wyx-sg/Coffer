// frontend/src/pages/sync/SyncCloudFolderCard.tsx — 6.5.15: the vault sits in
// a folder another tool also syncs, so rounds are paused until it moves.
import { useTranslation } from "react-i18next";
import { Cloud, FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { fsApi } from "@/lib/api/fs";
import { translateApiError } from "@/lib/api/errors";
import type { SyncStatus } from "@/lib/api/sync";
import { SyncBannerCard } from "./SyncBanner";
import { Body } from "./SyncProblemParts";

export function SyncCloudFolderCard({ status }: { status: SyncStatus }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const tool = status.synchroniser ?? t("sync.problem.cloud_folder.someTool");
  return (
    <SyncBannerCard
      icon={Cloud}
      tone="warn"
      title={t("sync.problem.cloud_folder.title", { tool })}
      testId="sync-problem"
    >
      <Body>
        <span className="font-mono text-xs text-text">{status.vault_path}</span>{" "}
        {t("sync.problem.cloud_folder.body", { tool })}
      </Body>
      <div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            void fsApi
              .reveal(status.vault_path)
              .catch((error: unknown) => toast.error(translateApiError(t, error)))
          }
        >
          <FolderOpen aria-hidden />
          {t("sync.problem.reveal")}
        </Button>
      </div>
    </SyncBannerCard>
  );
}
