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
//
// The active tab lives in the URL (`?tab=`), so a link can land on History
// and a reload comes back where it was.
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SyncHistoryTab } from "./SyncHistoryTab";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { SyncStatusTab } from "./SyncStatusTab";

const TABS = ["status", "history", "machines"] as const;
type SyncTab = (typeof TABS)[number];

function isSyncTab(value: string | null): value is SyncTab {
  return (TABS as readonly string[]).includes(value ?? "");
}

export function SyncPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: SyncTab = isSyncTab(requested) ? requested : "status";
  const setTab = (next: string) => {
    const search = new URLSearchParams(params);
    if (next === "status") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
  };

  return (
    <div className="space-y-8">
      <PageHeader icon={RefreshCw} title={t("sync.title")} subtitle={t("sync.subtitle")} />

      <Tabs value={tab} onValueChange={setTab}>
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
