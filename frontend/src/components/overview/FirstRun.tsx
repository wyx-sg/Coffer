// src/components/overview/FirstRun.tsx — what the Overview says before any agent is registered: connect one, then add what they share.
//
// Lists every supported agent type with whether it was found on this Mac,
// and one step forward (the Agents page, where connecting previews every file
// change before Coffer writes it). Below, the areas an agent shares, each
// with its first step. Knowledge is offered only while its feature is on.
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAgentTypes } from "@/lib/hooks/useAgentTypes";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { NAV_ENTRIES } from "@/lib/navigation";

const INSTALLED = new Set(["installed_active", "installed_never_run"]);

/** The areas agents share, in sidebar order, each with its first-step copy key. */
const SHARED: readonly { to: string; id: string; feature?: "knowledge" }[] = [
  { to: "/mcp-servers", id: "mcpServers" },
  { to: "/skills", id: "skills" },
  { to: "/knowledge", id: "knowledge", feature: "knowledge" },
  { to: "/model-providers", id: "providers" },
  { to: "/channels", id: "channels" },
];

export function FirstRun() {
  const { t } = useTranslation();
  const types = useAgentTypes();
  const knowledgeOn = useFeatureEnabled("knowledge");
  const shared = SHARED.filter((s) => !s.feature || knowledgeOn === true);

  return (
    <>
      <section
        aria-labelledby="overview-first-run"
        className="space-y-4 rounded-xl border border-border-subtle bg-surface-raised px-5 py-5"
      >
        <div className="space-y-1.5">
          <h2 id="overview-first-run" className="text-md font-semibold">
            {t("overview.firstRun.title")}
          </h2>
          <p className="max-w-prose text-sm text-text-muted">{t("overview.firstRun.body")}</p>
          <p className="max-w-prose text-sm text-text-muted">{t("overview.firstRun.preview")}</p>
        </div>
        {types.isPending ? (
          <div aria-busy className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-6 w-48" />
          </div>
        ) : types.isError ? (
          <p className="text-xs text-danger">{translateApiError(t, types.error)}</p>
        ) : (
          <ul className="space-y-2">
            {sortAgents(types.data).map((row) => {
              const found = INSTALLED.has(row.state);
              return (
                <li key={row.type} className="flex items-center gap-3">
                  <AgentBadge
                    type={row.type}
                    name={row.display_name}
                    state={found ? undefined : "not-installed"}
                    showName
                    tooltip={false}
                  />
                  <span className="text-xs text-text-muted">
                    {found ? t("overview.firstRun.found") : t("overview.firstRun.notInstalled")}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        <Button asChild>
          <Link to="/agents">
            {t("overview.firstRun.connect")}
            <ArrowRight aria-hidden />
          </Link>
        </Button>
      </section>

      <section aria-labelledby="overview-then" className="space-y-3">
        <h2 id="overview-then" className="text-sm font-semibold">
          {t("overview.firstRun.thenTitle")}
        </h2>
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {shared.map((s) => {
            const entry = NAV_ENTRIES.find((e) => e.to === s.to);
            if (!entry) return null;
            const Icon = entry.icon;
            return (
              <li
                key={s.id}
                className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-surface-raised px-4 py-3.5"
              >
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <Icon className="size-4 text-text-subtle" strokeWidth={1.75} aria-hidden />
                  {t(entry.labelKey)}
                </span>
                <span className="text-xs text-text-muted">
                  {t(`overview.firstRun.shared.${s.id}.body`)}
                </span>
                <Button asChild variant="outline" size="sm" className="mt-auto self-start">
                  <Link to={s.to}>{t(`overview.firstRun.shared.${s.id}.cta`)}</Link>
                </Button>
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
