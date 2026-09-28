// frontend/src/pages/sync/SyncSetupTab.tsx — Sync → Setup.
//
// Everything you configure once and then stop thinking about: which repository
// this vault converges with, and the master key another machine needs to
// decrypt what this one publishes. The machine registry is its own tab.
//
// The master key is here and not in the app's Settings for the same reason: its
// whole purpose is making another machine able to read what this one syncs, so
// it belongs beside the remote it is a key to.
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";
import { SyncRemoteCard } from "./SyncRemoteCard";

export function SyncSetupTab() {
  const { t } = useTranslation();
  const { data, isPending } = useSyncStatus();

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <SyncRemoteCard status={data ?? null} />
      <SyncMasterKeyCard />
    </div>
  );
}
