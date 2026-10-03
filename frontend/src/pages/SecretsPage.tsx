// src/pages/SecretsPage.tsx — /secrets: every stored and cited secret with what uses it (spec web-ui "Manage stored secrets on the Secrets page").
//
// One filterable, sortable list (search, status, owner type; or grouped by owner) under two
// banners: the changes waiting for approval, and the secrets this Mac has no value for (with
// Import master key). Each secret shows its own short name and who owns it in words. Add
// secret stores a standalone secret; Find plaintext keys moves
// values out of files into the store. Each row's ⋯ menu replaces, reveals (in
// the desktop app only), copies its reference, opens Activity, or deletes —
// which, for a secret something still uses, says what does instead. No value
// is ever on this page until Reveal is chosen.
import { useMemo, useState } from "react";
import { IdCard, Plus, RotateCcw, ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AddSecretDialog } from "@/components/secret/AddSecretDialog";
import { DeleteSecretDialog } from "@/components/secret/DeleteSecretDialog";
import { PendingApprovalsEntry } from "@/components/secret/PendingApprovalsEntry";
import { RefusedApprovalsEntry } from "@/components/secret/RefusedApprovalsEntry";
import { ReplaceSecretDialog } from "@/components/secret/ReplaceSecretDialog";
import { RevealSecretDialog } from "@/components/secret/RevealSecretDialog";
import { ScanSecretsDialog } from "@/components/secret/ScanSecretsDialog";
import type { SecretRowAction } from "@/components/secret/SecretRowMenu";
import { SecretsBrowser } from "@/components/secret/SecretsBrowser";
import { SecretsMissingBanner } from "@/components/secret/SecretsMissingBanner";
import { isMissingHere, refsWaiting } from "@/components/secret/secretRows";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import type { SecretRef } from "@/lib/api/secret";
import { translateApiError } from "@/lib/api/errors";
import { usePendingApprovals, useRefusedApprovals } from "@/lib/hooks/useApprovals";
import { useSecrets } from "@/lib/hooks/useSecrets";

type Open = { dialog: "add" | "scan" } | { dialog: SecretRowAction; row: SecretRef } | null;

export function SecretsPage() {
  const { t } = useTranslation();
  const secrets = useSecrets();
  const approvals = usePendingApprovals();
  const waiting = refsWaiting(approvals.data?.approvals);
  const refusedApprovals = useRefusedApprovals();
  const refused = useMemo(
    () => new Set((refusedApprovals.data?.approvals ?? []).flatMap((a) => (a.ref ? [a.ref] : []))),
    [refusedApprovals.data],
  );
  const [open, setOpen] = useState<Open>(null);
  const rows = secrets.data?.refs ?? [];
  const firstRun = !secrets.isPending && !secrets.error && rows.length === 0;

  const rowFor = (dialog: SecretRowAction) =>
    open && open.dialog === dialog && "row" in open ? open.row : null;
  const closeTo = (next: boolean) => {
    if (!next) setOpen(null);
  };
  const addButton = (
    <Button onClick={() => setOpen({ dialog: "add" })}>
      <Plus aria-hidden /> {t("secrets.add.open")}
    </Button>
  );
  const scanButton = (
    <Button variant="outline" onClick={() => setOpen({ dialog: "scan" })}>
      <ScanSearch aria-hidden /> {t("secrets.scan.open")}
    </Button>
  );

  return (
    <div className="space-y-6">
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

      <PendingApprovalsEntry />
      <RefusedApprovalsEntry />
      <SecretsMissingBanner count={rows.filter(isMissingHere).length} />

      {secrets.error ? (
        <EmptyState
          tone="error"
          title={t("secrets.loadFailed")}
          description={translateApiError(t, secrets.error)}
          action={
            <Button variant="outline" onClick={() => void secrets.refetch()}>
              <RotateCcw aria-hidden /> {t("common.retry")}
            </Button>
          }
        />
      ) : firstRun ? (
        <EmptyState
          icon={IdCard}
          title={t("secrets.empty.title")}
          description={t("secrets.empty.body")}
          action={addButton}
          secondaryAction={scanButton}
        />
      ) : (
        <SecretsBrowser
          rows={rows}
          waiting={waiting}
          refused={refused}
          isLoading={secrets.isPending}
          onAction={(dialog, row) => setOpen({ dialog, row })}
        />
      )}

      <AddSecretDialog
        open={open?.dialog === "add"}
        onOpenChange={closeTo}
        existing={rows}
        onReplaceInstead={(row) => setOpen({ dialog: "replace", row })}
      />
      <ScanSecretsDialog open={open?.dialog === "scan"} onOpenChange={closeTo} />
      <ReplaceSecretDialog row={rowFor("replace")} onOpenChange={closeTo} />
      <RevealSecretDialog row={rowFor("reveal")} onOpenChange={closeTo} />
      <DeleteSecretDialog row={rowFor("delete")} onOpenChange={closeTo} />
    </div>
  );
}
