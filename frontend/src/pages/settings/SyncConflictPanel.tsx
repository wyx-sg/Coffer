// frontend/src/pages/settings/SyncConflictPanel.tsx
// The conflict-resolution card shown on Settings → Sync only while the sync
// status is "conflicted": lists the conflicting paths and the ours/theirs
// resolution actions. Split out of SyncSettings to keep that page small; reads
// the sync status + resolve mutation directly so the parent stays lean.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useResolveSync, useSyncStatus } from "@/lib/hooks/useSync";

export function SyncConflictPanel() {
  const { t } = useTranslation();
  const { data: status } = useSyncStatus();
  const resolve = useResolveSync();

  if (status?.status !== "conflicted") return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.sync.conflicts")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="list-disc pl-5 text-sm text-foreground/70">
          {status.conflict_paths.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => resolve.mutate({ strategy: "ours", paths: [] })}>
            {t("settings.sync.resolveOurs")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => resolve.mutate({ strategy: "theirs", paths: [] })}
          >
            {t("settings.sync.resolveTheirs")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
