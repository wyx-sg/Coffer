// src/pages/CliDetailPage.tsx — one required command's page (`/clis/<command>`), one page with no tabs.
//
// Spec web-ui "Show every CLI a skill requires on the CLIs page": the header's
// status pill and Check again (which probes this command afresh), a banner
// naming the skills its problem breaks, then where it was found, its version
// against the minimum, the Homebrew command behind a confirmation, the login
// command to copy, and the skills that need it.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, RefreshCw, SquareTerminal } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { PageFallback } from "@/components/PageFallback";
import { PageHeader } from "@/components/PageHeader";
import { CliDetailSections } from "@/components/clis/CliDetailSections";
import { CliInstallDialog } from "@/components/clis/CliInstallDialog";
import { CliProblemBanner } from "@/components/clis/CliProblemBanner";
import { StatusPill } from "@/components/status/StatusPill";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import { translateApiError } from "@/lib/api/errors";
import { cliTone } from "@/lib/clis/format";
import { useCheckCli, useCli } from "@/lib/hooks/useClis";

export function CliDetailPage() {
  const { t } = useTranslation();
  const { command = "" } = useParams<{ command: string }>();
  const { data: cli, isPending, error } = useCli(command);
  const check = useCheckCli(command);
  const [installFor, setInstallFor] = useState<Cli | null>(null);
  const back = { to: "/clis", label: t("clis.detail.back") };

  if (isPending) return <PageFallback />;
  if (error || !cli) {
    return (
      <EmptyState
        icon={SquareTerminal}
        tone="error"
        title={t("clis.detail.notFound")}
        description={error ? translateApiError(t, error) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to="/clis">
              <ArrowLeft aria-hidden />
              {t("clis.detail.back")}
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={<span className="font-mono">{cli.command}</span>}
        badges={
          <>
            <StatusPill tone={cliTone(cli.status)}>{t(`clis.status.${cli.status}`)}</StatusPill>
            <HelpTip>
              <p className="text-xs">{t("clis.detail.help")}</p>
            </HelpTip>
          </>
        }
        subtitle={t("clis.detail.subtitle", {
          title: cli.title ?? cli.command,
          count: cli.needed_by.length,
        })}
        actions={
          <Button variant="outline" disabled={check.isPending} onClick={() => check.mutate()}>
            <RefreshCw aria-hidden className={check.isPending ? "animate-spin" : undefined} />
            {check.isPending ? t("clis.checking") : t("clis.checkAgain")}
          </Button>
        }
      />
      <CliProblemBanner cli={cli} onInstall={setInstallFor} />
      <CliDetailSections cli={cli} onInstall={setInstallFor} />
      <CliInstallDialog cli={installFor} onOpenChange={(open) => !open && setInstallFor(null)} />
    </div>
  );
}
