// frontend/src/pages/sync/SyncPage.tsx — the top-level Sync surface
// (spec vault-sync "Present a Sync page with Runs and Setup tabs").
//
// Sync is cross-cutting rather than a resource kind, and convergence is
// something a person opens deliberately rather than a setting they tweak once,
// so it is a page under System, not a Settings tab. `/settings/sync` redirects
// here.
//
// Two tabs: **Runs** (every round this machine has run, and anything one of
// them is waiting on) and **Setup** (the remote, the master key, the machine
// registry). Runs is the landing tab, because what a person opens Sync to find
// out is whether it is working.
//
// There were three. **Status** is gone, and its two banners with it: a conflict
// and a held round are not states beside the history, they are the newest row
// OF it — a held round is a round. Keeping them apart put one situation in two
// places and made it actionable in only one, so the answers now sit on the row
// that is waiting (`SyncHeldRoundActions`), gated on the vault actually
// waiting rather than on a row that merely ended held.
//
// **Machines** folded into Setup for the opposite reason: pointing at a
// remote, carrying the key over and watching the second machine appear are one
// errand, and the last step is how you know the first two worked.
//
// Only the tab in front queries: Radix unmounts the other, and Runs is handed
// `enabled` besides, so nothing is fetched and thrown away.
//
// The active tab lives in the URL (`?tab=`), so a link can land on Setup and a
// reload comes back where it was.
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SyncRunsTab } from "./SyncRunsTab";
import { SyncSetupTab } from "./SyncSetupTab";

const TABS = ["runs", "setup"] as const;
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
        </TabsList>
        <TabsContent value="runs" className="pt-6">
          <SyncRunsTab enabled={tab === "runs"} />
        </TabsContent>
        <TabsContent value="setup" className="pt-6">
          <SyncSetupTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
