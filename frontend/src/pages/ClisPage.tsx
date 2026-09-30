// src/pages/ClisPage.tsx — the CLIs page: every command a managed skill requires, problems first.
//
// Spec web-ui "Show every CLI a skill requires on the CLIs page". The header's
// Check again re-probes every command; the summary strip counts each status;
// the table keeps the daemon's problems-first order. Install… / Update… open
// the Homebrew confirmation (CliInstallDialog) — nothing runs from the list.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, SquareTerminal } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { PageHeader } from "@/components/PageHeader";
import { CliInstallDialog } from "@/components/clis/CliInstallDialog";
import { ClisEmptyState } from "@/components/clis/ClisEmptyState";
import { ClisSummary } from "@/components/clis/ClisSummary";
import { ClisTable } from "@/components/clis/ClisTable";
import { ClisWarnings } from "@/components/clis/ClisWarnings";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { useCheckClis, useClis } from "@/lib/hooks/useClis";

export function ClisPage() {
  const { t } = useTranslation();
  const { data, isPending, error, refetch } = useClis();
  const check = useCheckClis();
  const [installFor, setInstallFor] = useState<Cli | null>(null);
  const items = data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        icon={SquareTerminal}
        title={t("clis.title")}
        badges={
          <>
            {data ? (
              <span className="text-sm text-text-muted">
                {t("clis.count", { count: items.length })}
              </span>
            ) : null}
            <HelpTip>
              <p className="text-xs">{t("clis.help")}</p>
            </HelpTip>
          </>
        }
        subtitle={t("clis.subtitle")}
        actions={
          <Button variant="outline" disabled={check.isPending} onClick={() => check.mutate()}>
            <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
            {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
          </Button>
        }
      />

      {error ? (
        <EmptyState
          tone="error"
          icon={SquareTerminal}
          title={t("clis.loadFailed")}
          description={translateApiError(t, error)}
          action={
            <Button variant="outline" onClick={() => void refetch()}>
              {t("clis.checkAgain")}
            </Button>
          }
        />
      ) : !isPending && items.length === 0 ? (
        <>
          <ClisWarnings warnings={data?.warnings ?? []} />
          <ClisEmptyState />
        </>
      ) : (
        <>
          {items.length > 0 ? <ClisSummary items={items} /> : null}
          <ClisWarnings warnings={data?.warnings ?? []} />
          <ClisTable items={items} isLoading={isPending} onInstall={setInstallFor} />
        </>
      )}

      <CliInstallDialog cli={installFor} onOpenChange={(open) => !open && setInstallFor(null)} />
    </div>
  );
}
