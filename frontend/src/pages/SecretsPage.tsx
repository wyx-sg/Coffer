// src/pages/SecretsPage.tsx — /secrets[/<ref>]: every stored and cited secret, beside the open one (spec web-ui "Manage stored secrets on the Secrets page").
//
// The list pane filters by name, description and reference and by status; the open secret
// (`/secrets/<ref>`, the ref URL-encoded) has its own detail pane.
// Above the split, up to two banners: no value on this Mac (Add value(s)), then changes waiting
// for approval (Review) — each closable with × = Ignore, shared with Overview. Add secret stores a
// standalone secret under an id Coffer mints; Find plaintext keys moves values out of skills and
// MCP servers into the store. No value is ever on this page until Reveal is chosen.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { IdCard, Plus, ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AddSecretDialog } from "@/components/secret/AddSecretDialog";
import { AddValuesDialog } from "@/components/secret/AddValuesDialog";
import { ApprovalsOffNote } from "@/components/secret/ApprovalsOffNote";
import { ScanSecretsDialog } from "@/components/secret/ScanSecretsDialog";
import { SecretPane } from "@/components/secret/SecretPane";
import { SecretsBanners } from "@/components/secret/SecretsBanners";
import { SecretsList } from "@/components/secret/SecretsList";
import { isMissingHere } from "@/components/secret/secretRows";
import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { NothingSelected } from "@/components/ListPaneStates";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { Button } from "@/components/ui/button";
import { usePendingApprovals } from "@/lib/hooks/useApprovals";
import { useSecrets } from "@/lib/hooks/useSecrets";
import { cn } from "@/lib/utils";

type Open = "add" | "scan" | "values" | null;

export function SecretsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id = "" } = useParams<{ id?: string }>();
  const secrets = useSecrets();
  const approvals = usePendingApprovals();
  const waitingApprovals = approvals.data?.approvals ?? [];
  const [open, setOpen] = useState<Open>(null);
  const rows = secrets.data?.refs ?? [];
  const match = id ? rows.find((r) => r.ref === id) : undefined;
  const missing = rows.filter(isMissingHere);
  const firstRun = !secrets.isPending && !secrets.error && rows.length === 0 && !id;

  const closeTo = (next: boolean) => {
    if (!next) setOpen(null);
  };
  const addButton = (
    <Button onClick={() => setOpen("add")}>
      <Plus aria-hidden /> {t("secrets.add.open")}
    </Button>
  );
  const scanButton = (
    <Button variant="outline" onClick={() => setOpen("scan")}>
      <ScanSearch aria-hidden /> {t("secrets.scan.open")}
    </Button>
  );

  // While the list loads or failed (its pane shows why), the right pane stays empty.
  let pane: JSX.Element | null;
  if (secrets.error || secrets.isPending) {
    pane = null;
  } else if (match) {
    pane = (
      <SecretPane
        key={match.ref}
        row={match}
        onDeleted={() => navigate("/secrets", { replace: true })}
      />
    );
  } else if (id) {
    pane = <DetailNotFound kind="secrets" id={id} backTo="/secrets" icon={IdCard} />;
  } else {
    pane = <NothingSelected icon={IdCard} />;
  }

  return (
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "flex shrink-0 flex-col gap-4 pb-4")}>
        <PageHeader
          title={t("secrets.title")}
          subtitle={t("secrets.subtitle")}
          actions={
            firstRun ? null : (
              <div className="flex flex-wrap items-center gap-2">
                {scanButton}
                {addButton}
              </div>
            )
          }
        />
        <ApprovalsOffNote />
        <SecretsBanners
          rows={rows}
          approvals={waitingApprovals}
          onAddValues={() => setOpen("values")}
        />
      </div>

      {firstRun ? (
        <div className="flex min-h-0 flex-1 items-start justify-center overflow-y-auto px-8 pb-20">
          <EmptyState
            icon={IdCard}
            title={t("secrets.empty.title")}
            description={t("secrets.empty.body")}
            action={addButton}
            secondaryAction={scanButton}
          />
        </div>
      ) : (
        <SplitView
          storageKey="secrets.list"
          defaultListWidth={340}
          label={t("splitView.resizeList")}
          className="min-h-0 flex-1 border-t border-border-subtle"
          listClassName="bg-surface-sidebar"
          detailClassName="overflow-y-auto"
          list={
            <SecretsList
              rows={rows}
              isLoading={secrets.isPending}
              error={secrets.error}
              onRetry={() => void secrets.refetch()}
              selectedRef={match?.ref ?? null}
            />
          }
          detail={<div className="px-7 pb-5 pt-5">{pane}</div>}
        />
      )}

      <AddSecretDialog open={open === "add"} onOpenChange={closeTo} />
      <ScanSecretsDialog open={open === "scan"} onOpenChange={closeTo} />
      <AddValuesDialog open={open === "values"} onOpenChange={closeTo} rows={missing} />
    </div>
  );
}
