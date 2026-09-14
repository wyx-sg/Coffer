// frontend/src/pages/sync/SyncPage.tsx — the top-level Sync surface
// (spec vault-sync `## Surfaces`).
//
// Sync is cross-cutting rather than a resource kind, and convergence is
// something a person opens deliberately rather than a setting they tweak once,
// so it is a page under System, not a Settings tab. `/settings/sync` redirects
// here.
//
// Three tabs: **Status** (the remote, the master key, and anything waiting on
// the user), **History** (every round this machine has run) and **Machines**
// (the registry). Status answers "what is it doing"; History answers "what has
// it been doing", which one round's worth of prose on Status never could.
//
// Conflicts and held rounds stay BANNERS on Status rather than becoming a tab
// of their own — they are states the vault passes through, and a permanent tab
// for them would read as a place you are meant to visit.
//
// Only the tab in front queries: Radix unmounts the others, and History is
// handed `enabled` besides, so nothing is fetched and thrown away.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SyncHistoryTab } from "./SyncHistoryTab";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { SyncStatusTab } from "./SyncStatusTab";

type SyncTab = "status" | "history" | "machines";

export function SyncPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<SyncTab>("status");

  return (
    <div className="space-y-8">
      <PageHeader icon={RefreshCw} title={t("sync.title")} subtitle={t("sync.subtitle")} />

      <Tabs value={tab} onValueChange={(v) => setTab(v as SyncTab)}>
        <TabsList>
          <TabsTrigger value="status">{t("sync.tabs.status")}</TabsTrigger>
          <TabsTrigger value="history">{t("sync.tabs.history")}</TabsTrigger>
          <TabsTrigger value="machines">{t("sync.tabs.machines")}</TabsTrigger>
        </TabsList>
        <TabsContent value="status" className="pt-6">
          <SyncStatusTab />
        </TabsContent>
        <TabsContent value="history" className="pt-6">
          <SyncHistoryTab enabled={tab === "history"} />
        </TabsContent>
        <TabsContent value="machines" className="pt-6">
          <SyncMachinesTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
