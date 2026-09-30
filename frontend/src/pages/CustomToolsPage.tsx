// src/pages/CustomToolsPage.tsx — the Custom tools page (/custom-tools, /custom-tools/:group): the groups of
// HTTP API tools sectioned by health beside the selected group, one Add custom tool action.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Wrench } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { AddCustomToolDialog } from "@/components/custom-tools/AddCustomToolDialog";
import { CustomToolsFirstRun } from "@/components/custom-tools/CustomToolsFirstRun";
import { GroupList } from "@/components/custom-tools/GroupList";
import { GroupPane } from "@/components/custom-tools/GroupPane";
import type { AddWay } from "@/components/custom-tools/addFlow";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { useCustomToolGroups } from "@/lib/hooks/useCustomTools";

export function CustomToolsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { group: selected } = useParams<{ group?: string }>();
  const { data, isPending, error, refetch } = useCustomToolGroups();
  const [adding, setAdding] = useState<AddWay | null>(null);
  const groups = data ?? [];
  const firstRun = !isPending && !error && groups.length === 0;
  const toolCount = groups.reduce((n, g) => n + g.tools.length, 0);

  const addButton = (
    <Button onClick={() => setAdding("import")}>
      <Plus aria-hidden />
      {t("customTools.add.action")}
    </Button>
  );

  return (
    <div className="relative -mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
      <div className="border-b border-border-subtle px-6 py-5 md:px-8">
        <PageHeader
          icon={Wrench}
          title={t("customTools.title")}
          subtitle={
            data && groups.length > 0
              ? t("customTools.list.counts", {
                  groups: t("customTools.list.groupCount", { count: groups.length }),
                  tools: t("customTools.list.toolCount", { count: toolCount }),
                })
              : undefined
          }
          actions={firstRun ? null : addButton}
        />
      </div>
      {error ? (
        <EmptyState
          icon={Wrench}
          tone="error"
          title={t("customTools.list.loadFailed")}
          description={translateApiError(t, error)}
          action={
            <Button variant="outline" onClick={() => void refetch()}>
              {t("common.retry")}
            </Button>
          }
        />
      ) : firstRun ? (
        <div className="overflow-y-auto">
          <CustomToolsFirstRun onAdd={setAdding} />
        </div>
      ) : (
        <SplitView
          storageKey="customTools.list"
          label={t("splitView.resizeList")}
          className="min-h-0 flex-1"
          listClassName="border-r-0 bg-surface-sidebar"
          detailClassName="overflow-y-auto"
          list={
            <GroupList
              groups={groups}
              loading={isPending}
              selected={selected}
              onOpen={(name) => navigate(`/custom-tools/${encodeURIComponent(name)}`)}
            />
          }
          detail={
            selected ? (
              <GroupPane key={selected} name={selected} />
            ) : (
              <EmptyState
                icon={Wrench}
                title={t("customTools.list.pickTitle")}
                description={t("customTools.list.pickBody")}
              />
            )
          }
        />
      )}
      <AddCustomToolDialog
        open={adding !== null}
        onOpenChange={(open) => !open && setAdding(null)}
        groups={groups.map((g) => g.name)}
        initialWay={adding ?? "import"}
      />
    </div>
  );
}
