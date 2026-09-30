// src/components/overview/FirstRunAgents.tsx — the first-run card: the supported agents Coffer looked for, and connecting them.
//
// Every supported agent is a row: its badge, name and config folder, and
// whether it was found on this Mac. A found agent carries a tick (all ticked
// to start); "Review and connect N agents" opens the connection review
// (AgentConnectionChangeDialog, the one the Agents page uses), which shows
// every file change before Coffer writes it. When none was found the card
// says so, and its first step is Scan again (Overview boards 1.3.03, 1.3.07).
// Either way "Add an agent by hand" leads to the Agents page, where an
// agent's config folder can be chosen.
import { Plug, RefreshCw, Search, UserPlus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { AgentConnectionChangeDialog } from "@/components/agents/connect/AgentConnectionChangeDialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { AgentTypeOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { useAgentInstallHandoff, useAgentTypes } from "@/lib/hooks/useAgentTypes";
import { formatClock } from "@/lib/overview/time";

const INSTALLED = new Set(["installed_active", "installed_never_run"]);
const isFound = (row: AgentTypeOut) => INSTALLED.has(row.state);

export function FirstRunAgents() {
  const { t } = useTranslation();
  const types = useAgentTypes();
  const rows = types.data ? sortAgents(types.data) : [];
  const found = rows.filter(isFound);
  // Types the person unticked; everything found starts ticked.
  const [unticked, setUnticked] = useState<ReadonlySet<string>>(new Set());
  const [reviewing, setReviewing] = useState<AgentTypeOut[] | null>(null);
  const chosen = found.filter((row) => !unticked.has(row.type));
  const none = types.isSuccess && found.length === 0;
  // With none installed, installing one is handed to the person's assistant as
  // a prompt the daemon writes (Principle IV); there is no agent here to ask.
  const installPrompt = useAgentInstallHandoff(none).data ?? null;
  const scannedAt = types.dataUpdatedAt > 0 ? new Date(types.dataUpdatedAt).toISOString() : null;
  const toggle = (type: string) =>
    setUnticked((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  const scan = () => void types.refetch();

  return (
    <section
      aria-labelledby="overview-first-run"
      className="flex flex-col gap-6 rounded-xl border border-border bg-surface-raised p-6 lg:flex-row lg:gap-8"
    >
      <div className="flex shrink-0 flex-col gap-2.5 lg:w-[330px]">
        <span className="inline-flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
          {none ? (
            <Search className="size-5" strokeWidth={1.75} aria-hidden />
          ) : (
            <Plug className="size-5" strokeWidth={1.75} aria-hidden />
          )}
        </span>
        <h2 id="overview-first-run" className="text-md font-bold text-text">
          {t(none ? "overview.firstRun.noneTitle" : "overview.firstRun.title")}
        </h2>
        <p className="text-sm leading-[1.55] text-text-muted">
          {none
            ? t("overview.firstRun.noneBody", {
                names: rows.map((r) => r.display_name).join(t("overview.firstRun.and")),
              })
            : types.isSuccess
              ? t("overview.firstRun.foundBody", { count: found.length })
              : t("overview.firstRun.body")}
        </p>
        <p className="text-xs leading-normal text-text-subtle">
          {t(none ? "overview.firstRun.confirmOnly" : "overview.firstRun.preview")}
        </p>
      </div>

      <div className="flex min-w-0 grow flex-col gap-3">
        {types.isPending ? (
          <div aria-busy className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : types.isError ? (
          <p className="text-xs text-danger">{translateApiError(t, types.error)}</p>
        ) : (
          <ul className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border">
            {rows.map((row) => (
              <AgentRow
                key={row.type}
                row={row}
                ticked={isFound(row) && !unticked.has(row.type)}
                onToggle={() => toggle(row.type)}
              />
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {none ? (
            <>
              <Button onClick={scan} loading={types.isFetching}>
                <RefreshCw aria-hidden />
                {t("overview.firstRun.scan")}
              </Button>
              {installPrompt ? <AgentHandoff prompt={installPrompt} /> : null}
            </>
          ) : (
            <Button disabled={chosen.length === 0} onClick={() => setReviewing(chosen)}>
              <Plug aria-hidden />
              {t("overview.firstRun.connect", { count: chosen.length })}
            </Button>
          )}
          <Button asChild variant="ghost">
            <Link to="/agents">
              <UserPlus aria-hidden />
              {t("overview.firstRun.byHand")}
            </Link>
          </Button>
          <span className="ml-auto text-xs text-text-subtle">
            {none ? (
              <>
                {t("overview.firstRun.lastScanned")}{" "}
                {scannedAt ? <time dateTime={scannedAt}>{formatClock(scannedAt)}</time> : null}
                {" · "}
                <span className="font-mono">
                  {rows.map((r) => abbreviateHomePath(r.config_dir)).join(", ")}
                </span>
              </>
            ) : (
              <>
                {t("overview.firstRun.looked")}
                {" · "}
                <button
                  type="button"
                  onClick={scan}
                  className="rounded-xs font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                >
                  {t("overview.firstRun.scan")}
                </button>
              </>
            )}
          </span>
        </div>
      </div>
      <AgentConnectionChangeDialog
        request={reviewing ? { kind: "add", rows: reviewing } : null}
        onClose={() => setReviewing(null)}
      />
    </section>
  );
}

function AgentRow({
  row,
  ticked,
  onToggle,
}: {
  row: AgentTypeOut;
  ticked: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const found = isFound(row);
  return (
    <li>
      <label className="flex min-h-12 items-center gap-3 px-3.5 py-1.5">
        {found ? (
          <Checkbox
            checked={ticked}
            onChange={onToggle}
            aria-label={t("overview.firstRun.tick", { name: row.display_name })}
          />
        ) : null}
        <AgentBadge type={row.type} name={row.display_name} tooltip={false} />
        <span className="text-sm font-label text-text">{row.display_name}</span>
        <span className="truncate font-mono text-xs text-text-muted">
          {abbreviateHomePath(row.config_dir)}
        </span>
        <span className="ml-auto whitespace-nowrap text-xs text-text-muted">
          {t(found ? "overview.firstRun.found" : "overview.firstRun.notFound")}
        </span>
      </label>
    </li>
  );
}
