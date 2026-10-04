// src/pages/ClisPage.tsx — the CLIs page (/clis, /clis/:command): every command-line tool, beside the selected one.
//
// Spec web-ui "Show every CLI a skill requires on the CLIs page". A tool is
// listed because a skill or MCP server requires it, or because the person added
// it by hand (Add CLI: no skill needed). The header holds Check again (the
// primary button, which re-probes every tool) and Add CLI; on the first run
// there are none and the empty state carries Add CLI. Skipped `requires:`
// entries are one grey line under the subtitle. The list pane groups the tools
// into Needs attention (problems first, the daemon's order) and Ready; the
// detail pane shows the command in the address, or the first row when there is
// none. A command that needs the person offers the daemon's prompt for their
// agent — nothing installs or logs in from here.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, RefreshCw } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { AddCliDialog } from "@/components/clis/AddCliDialog";
import { CliPane } from "@/components/clis/CliPane";
import { ClisEmptyState } from "@/components/clis/ClisEmptyState";
import { ClisList } from "@/components/clis/ClisList";
import { ClisWarnings } from "@/components/clis/ClisWarnings";
import { Button } from "@/components/ui/button";
import { useCheckClis, useClis } from "@/lib/hooks/useClis";

export function ClisPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { command } = useParams<{ command?: string }>();
  const { data, isPending, error, refetch } = useClis();
  const check = useCheckClis();
  const [adding, setAdding] = useState(false);
  const items = data?.items ?? [];
  const warnings = data?.warnings ?? [];
  const selected = command ?? items[0]?.command ?? null;
  const firstRun = !isPending && !error && items.length === 0 && !command;

  let body: JSX.Element;
  if (firstRun) {
    body = (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-8 pb-20">
        <ClisEmptyState onAdd={() => setAdding(true)} />
      </div>
    );
  } else {
    body = (
      <SplitView
        storageKey="clis.list"
        defaultListWidth={300}
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        listClassName="bg-surface-sidebar"
        detailClassName="overflow-y-auto"
        list={
          <ClisList
            items={items}
            loading={isPending}
            error={error}
            onRetry={() => void refetch()}
            selected={selected}
            onOpen={(c) => navigate(`/clis/${encodeURIComponent(c)}`)}
          />
        }
        detail={
          <div className="px-7 py-5">
            {selected ? (
              <CliPane
                key={selected}
                command={selected}
                listed={items.find((c) => c.command === selected)}
                onRemoved={() => navigate("/clis")}
              />
            ) : null}
          </div>
        }
      />
    );
  }

  return (
    <div className="-mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
      <div className="flex shrink-0 flex-col gap-1.5 px-6 py-5 md:px-8">
        <PageHeader
          title={t("clis.title")}
          subtitle={t("clis.subtitle")}
          actions={
            firstRun ? undefined : (
              <>
                <Button disabled={check.isPending} onClick={() => check.mutate()}>
                  <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
                  {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
                </Button>
                <Button variant="outline" onClick={() => setAdding(true)}>
                  <Plus aria-hidden />
                  {t("clis.addTool")}
                </Button>
              </>
            )
          }
        />
        <ClisWarnings warnings={warnings} />
      </div>
      {body}
      <AddCliDialog
        open={adding}
        onOpenChange={setAdding}
        onSaved={(c) => navigate(`/clis/${encodeURIComponent(c)}`)}
      />
    </div>
  );
}
