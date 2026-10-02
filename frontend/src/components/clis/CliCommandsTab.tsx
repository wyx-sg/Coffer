// src/components/clis/CliCommandsTab.tsx — a tool's Commands tab: its whole interface, read from its own help.
//
// What the daemon kept for this version of the tool shows at once; when
// nothing is kept the pane has already asked the daemon to read it (which runs
// only the tool's `--help`), so the tab fills itself in, with a loading line
// while it runs. Read again replaces the tree. Failures — a tool that prints
// no help, a timeout, a daemon error — say so and offer a retry; a tree cut
// by the depth, size or time bound says that too. The open command is the
// page's `?node=`. Left: the command tree (SplitView, foldable); right: the
// open command.
import { RefreshCw, SquareTerminal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";

import { EmptyState } from "@/components/EmptyState";
import { SplitView } from "@/components/SplitView";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import type { CliInterface } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { buildTree, flatten } from "@/lib/clis/tree";
import type { useCliInterfaceAuto } from "@/lib/hooks/useClis";
import { formatDateTime } from "@/lib/utils";
import { CliCommandTree } from "./CliCommandTree";
import { CliNodeDetail } from "./CliNodeDetail";

interface Props {
  command: string;
  /** The tool's interface and its reader (`useCliInterfaceAuto`), owned by the pane. */
  iface: ReturnType<typeof useCliInterfaceAuto>;
}

export function CliCommandsTab({ command, iface }: Props) {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const { query, read } = iface;
  const data: CliInterface | undefined = query.data;

  if (query.error) {
    return (
      <EmptyState
        tone="error"
        icon={SquareTerminal}
        title={t("clis.commands.loadFailed")}
        description={translateApiError(t, query.error)}
        action={
          <Button variant="outline" onClick={() => void query.refetch()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  }
  if (read.error && !read.isPending && data?.status !== "ok") {
    return (
      <EmptyState
        tone="error"
        icon={SquareTerminal}
        title={t("clis.commands.readFailed")}
        description={translateApiError(t, read.error)}
        action={
          <Button variant="outline" onClick={() => read.mutate()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  }
  if (!data || data.status === "not_read" || read.isPending) {
    return (
      <div className="space-y-3" role="status" aria-label={t("clis.commands.reading")}>
        <p className="flex items-center gap-2 text-sm text-text-muted">
          <Spinner /> {t("clis.commands.reading")}
        </p>
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-8 w-2/3" />
      </div>
    );
  }
  const readAgain = (
    <Button variant="outline" size="sm" disabled={read.isPending} onClick={() => read.mutate()}>
      <RefreshCw aria-hidden />
      {t("clis.commands.readAgain")}
    </Button>
  );
  if (data.status !== "ok") {
    const unavailable = data.status === "unavailable";
    return (
      <EmptyState
        icon={SquareTerminal}
        title={t(unavailable ? "clis.commands.unavailable" : "clis.commands.noHelpTitle")}
        description={data.message ?? undefined}
        action={unavailable ? undefined : readAgain}
      />
    );
  }

  const root = buildTree(data.nodes);
  if (!root) return null;
  const all = flatten(root);
  const known = new Set(all.map((n) => n.key));
  const wanted = params.get("node") ?? "";
  const selected = known.has(wanted) ? wanted : "";
  const entry = all.find((n) => n.key === selected) ?? root;
  const select = (key: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (key === "") next.delete("node");
        else next.set("node", key);
        return next;
      },
      { replace: true },
    );

  return (
    <div className="flex h-[min(72vh,760px)] min-h-[380px] flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-text-muted">
          {t("clis.commands.summary", {
            count: all.length,
            when: data.discovered_at ? formatDateTime(data.discovered_at) : "—",
          })}
        </p>
        {readAgain}
      </div>
      {read.error ? (
        <Alert variant="error">
          <AlertDescription>{translateApiError(t, read.error)}</AlertDescription>
        </Alert>
      ) : null}
      {data.incomplete ? (
        <Alert variant="info">
          <AlertDescription>{t("clis.commands.incomplete")}</AlertDescription>
        </Alert>
      ) : null}
      <SplitView
        storageKey="clis.commands"
        defaultListWidth={260}
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1 overflow-hidden rounded-xl border border-border-subtle"
        listClassName="bg-surface-sidebar"
        detailClassName="overflow-y-auto"
        list={
          <CliCommandTree command={command} root={root} selected={entry.key} onSelect={select} />
        }
        detail={
          <CliNodeDetail
            key={entry.key}
            command={command}
            entry={entry}
            known={known}
            onOpen={select}
          />
        }
      />
    </div>
  );
}
