// frontend/src/pages/sync/SyncPage.tsx — the top-level Sync surface
// (spec vault-sync "Present a Sync page with Runs, Setup and Machines tabs").
//
// Sync is cross-cutting rather than a resource kind, and syncing is something
// a person opens deliberately rather than a setting they tweak once, so it is a
// page under System, not a Settings tab. `/settings/sync` redirects here.
//
// Three tabs: **Runs** (whether sync is working, anything it is waiting on a
// person for, what is waiting to push, and every round), **Setup** (the remote
// and the master key) and **Machines** (the registry). Runs is the landing
// tab, because what a person opens Sync to find out is whether it is working —
// and a stopped round, a held deletion or a join is answered there, above the
// history it belongs to, not on a tab of its own.
//
// Only the tab in front queries its history: Radix unmounts the others, and
// Runs is handed `enabled` besides.
//
// The active tab lives in the URL (`?tab=`), so a link can land on Setup and a
// reload comes back where it was.
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SyncRunsTab } from "./SyncRunsTab";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { SyncSetupTab } from "./SyncSetupTab";

const TABS = ["runs", "setup", "machines"] as const;
type SyncTab = (typeof TABS)[number];

function isSyncTab(value: string | null): value is SyncTab {
  return (TABS as readonly string[]).includes(value ?? "");
}

export function SyncPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: SyncTab = isSyncTab(requested) ? requested : "runs";
  const setTab = (next: string) => {
    const search = new URLSearchParams(params);
    // The landing tab carries no parameter, so the page's own URL is the
    // shortest one and a stale `?tab=status` link lands somewhere real.
    if (next === "runs") search.delete("tab");
    else search.set("tab", next);
    setParams(search, { replace: true });
  };

  return (
    <div className="space-y-8">
      <PageHeader icon={RefreshCw} title={t("sync.title")} subtitle={t("sync.subtitle")} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="runs">{t("sync.tabs.runs")}</TabsTrigger>
          <TabsTrigger value="setup">{t("sync.tabs.setup")}</TabsTrigger>
          <TabsTrigger value="machines">{t("sync.tabs.machines")}</TabsTrigger>
        </TabsList>
        <TabsContent value="runs" className="pt-6">
          <SyncRunsTab enabled={tab === "runs"} />
        </TabsContent>
        <TabsContent value="setup" className="pt-6">
          <SyncSetupTab />
        </TabsContent>
        <TabsContent value="machines" className="pt-6">
          <SyncMachinesTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
