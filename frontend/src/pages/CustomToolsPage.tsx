// src/pages/CustomToolsPage.tsx — the Custom tools page (/custom-tools, /custom-tools/:group): the groups of
// HTTP API tools sectioned by health beside the selected group, one Add custom tool action. With no
// group yet it is the first-run panel alone, no list.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Wrench } from "lucide-react";

import { NothingSelected } from "@/components/ListPaneStates";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { AddCustomToolDialog } from "@/components/custom-tools/AddCustomToolDialog";
import { CustomToolsFirstRun } from "@/components/custom-tools/CustomToolsFirstRun";
import { GroupList } from "@/components/custom-tools/GroupList";
import { GroupPane } from "@/components/custom-tools/GroupPane";
import type { AddStart } from "@/components/custom-tools/addFlow";
import { Button } from "@/components/ui/button";
import { useCustomToolGroups } from "@/lib/hooks/useCustomTools";

export function CustomToolsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { group: selected } = useParams<{ group?: string }>();
  const { data, isPending, error, refetch } = useCustomToolGroups();
  const [adding, setAdding] = useState<AddStart | null>(null);
  const groups = data ?? [];
  const firstRun = !isPending && !error && groups.length === 0;

  return (
    <div className="relative -mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
      <div className="shrink-0 border-b border-border-subtle px-6 py-3">
        <PageHeader
          title={t("customTools.title")}
          subtitle={t("customTools.subtitle")}
          actions={
            <Button onClick={() => setAdding({})}>
              <Plus aria-hidden />
              {t("customTools.add.action")}
            </Button>
          }
        />
      </div>
      {firstRun ? (
        <div className="flex flex-1 items-center overflow-y-auto">
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
              error={error}
              onRetry={() => void refetch()}
              selected={selected}
              onOpen={(name) => navigate(`/custom-tools/${encodeURIComponent(name)}`)}
            />
          }
          detail={
            error || isPending ? null : selected ? (
              <GroupPane
                key={selected}
                name={selected}
                onAddRequest={() => setAdding({ target: selected, step: "request" })}
              />
            ) : (
              <NothingSelected
                icon={Wrench}
                addLabel={t("customTools.add.action")}
                onAdd={() => setAdding({})}
              />
            )
          }
        />
      )}
      <AddCustomToolDialog
        open={adding !== null}
        onOpenChange={(open) => !open && setAdding(null)}
        groups={groups}
        start={adding ?? undefined}
      />
    </div>
  );
}
