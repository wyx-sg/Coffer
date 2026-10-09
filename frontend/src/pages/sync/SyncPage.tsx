// frontend/src/pages/sync/SyncPage.tsx — the top-level Sync surface
// (spec vault-sync "Present a Sync page with Status, Machines and Remote tabs").
//
// Sync is cross-cutting rather than a resource kind, and syncing is something
// a person opens deliberately rather than a setting they tweak once, so it is a
// page under System, not a Settings tab.
//
// It answers "is this Mac in sync?" in one state (`syncPageState.ts`), which
// the header's pill and button and the Status tab's banner all read. Three
// tabs: **Status** (the landing tab — the state, the areas line, anything a
// stopped round or a join is waiting on, and every round), **Machines** (the
// registry) and **Remote** (the repository, its secret and the vault). A Mac
// with no remote, or one that has not joined it yet, has no tabs: the header
// says "Not set up" and the body is the setup flow.
//
// The active tab lives in the URL (`?tab=`), so a link can land on Remote and
// a reload comes back where it was; Status carries no parameter, and an old
// `?tab=runs` or `?tab=setup` lands on it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { RotateCcw } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { useRunSync, useSyncStatus } from "@/lib/hooks/useSync";
import { SyncHeader } from "./SyncHeader";
import { SyncMachinesTab } from "./SyncMachinesTab";
import { SyncRemoteTab } from "./SyncRemoteTab";
import { SyncSetup } from "./SyncSetup";
import { SyncStatusTab } from "./SyncStatusTab";
import { syncState } from "./syncPageState";

const TABS = ["status", "machines", "remote"] as const;
type SyncTab = (typeof TABS)[number];

function isSyncTab(value: string | null): value is SyncTab {
  return (TABS as readonly string[]).includes(value ?? "");
}

export function SyncPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const { data: status, error, isPending, isFetching, refetch } = useSyncStatus();
  const run = useRunSync();
  // When this page asked for a round, until the status says one is running.
  const [startedAt, setStartedAt] = useState<string | null>(null);

  const requested = params.get("tab");
  const tab: SyncTab = isSyncTab(requested) ? requested : "status";
  const setTab = (next: string) => {
    const search = new URLSearchParams(params);
    // The landing tab carries no parameter, so the page's own URL is the
    // shortest one and a stale `?tab=runs` link lands somewhere real.
    if (next === "status") search.delete("tab");
    else search.set("tab", next);
    // A focus hint belongs to the link that carried it, not to the next tab.
    search.delete("focus");
    setParams(search, { replace: true });
  };

  if (!status) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("sync.title")} />
        {isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <EmptyState
            tone="error"
            title={t("sync.loadFailed")}
            description={translateApiError(t, error)}
            action={
              <Button variant="outline" onClick={() => void refetch()}>
                <RotateCcw aria-hidden /> {t("common.retry")}
              </Button>
            }
          />
        )}
      </div>
    );
  }

  const state = syncState(status, run.isPending);
  const runNow = () => {
    setStartedAt(new Date().toISOString());
    run.mutate(undefined, { onSettled: () => setStartedAt(null) });
  };

  if (state.kind === "setup") {
    return (
      <div className="space-y-6">
        <SyncHeader state={state} remote={status.remote} onRun={runNow} />
        <SyncSetup status={status} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SyncHeader state={state} remote={status.remote} onRun={runNow} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          {TABS.map((name) => (
            <TabsTrigger key={name} value={name}>
              {t(`sync.tabs.${name}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="status" className="pt-5">
          <SyncStatusTab
            status={status}
            state={state}
            startedAt={startedAt}
            onRecheck={() => void refetch()}
            rechecking={isFetching}
          />
        </TabsContent>
        <TabsContent value="machines" className="pt-5">
          <SyncMachinesTab />
        </TabsContent>
        <TabsContent value="remote" className="pt-5">
          <SyncRemoteTab status={status} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
