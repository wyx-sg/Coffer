// frontend/src/pages/sync/SyncPage.tsx — the top-level Sync surface
// (spec vault-sync `## Surfaces`).
//
// Sync is cross-cutting rather than a resource kind, and convergence is
// something a person opens deliberately rather than a setting they tweak once,
// so it is a page under System, not a Settings tab. `/settings/sync` redirects
// here.
//
// Two tabs, and only two: **Status** (the remote, the round, the master key)
// and **Machines** (the registry). Conflicts and held rounds are BANNERS on
// Status rather than a third tab — they are states the vault passes through,
// and a permanent tab for them would read as a place you are meant to visit.
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { SyncStatusTab } from "./SyncStatusTab";

export function SyncPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-8">
      <PageHeader icon={RefreshCw} title={t("sync.title")} subtitle={t("sync.subtitle")} />

      <Tabs defaultValue="status">
        <TabsList>
          <TabsTrigger value="status">{t("sync.tabs.status")}</TabsTrigger>
          <TabsTrigger value="machines">{t("sync.tabs.machines")}</TabsTrigger>
        </TabsList>
        <TabsContent value="status" className="pt-6">
          <SyncStatusTab />
        </TabsContent>
        <TabsContent value="machines" className="pt-6">
          <SyncMachinesTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
