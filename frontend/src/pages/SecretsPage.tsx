// src/pages/SecretsPage.tsx — /secrets: every stored and cited secret with what uses it (spec web-ui "Manage stored secrets on the Secrets page").
//
// One list in two groups — in use, and not used by anything — searched by
// name, under two banners: the changes waiting for approval, and the secrets
// this Mac has no value for (with Import master key). Add secret stores a standalone secret; Find plaintext keys moves
// values out of files into the store. Each row's ⋯ menu replaces, reveals (in
// the desktop app only), copies its reference, opens Activity, or deletes —
// which, for a secret something still uses, says what does instead. No value
// is ever on this page until Reveal is chosen.
import { useState } from "react";
import { KeyRound, Plus, RotateCcw, ScanSearch } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AddSecretDialog } from "@/components/credentials/AddSecretDialog";
import { DeleteSecretDialog } from "@/components/credentials/DeleteSecretDialog";
import { PendingApprovalsEntry } from "@/components/credentials/PendingApprovalsEntry";
import { ReplaceSecretDialog } from "@/components/credentials/ReplaceSecretDialog";
import { RevealSecretDialog } from "@/components/credentials/RevealSecretDialog";
import { ScanSecretsDialog } from "@/components/credentials/ScanSecretsDialog";
import type { SecretRowAction } from "@/components/credentials/SecretRowMenu";
import { SecretsGroups } from "@/components/credentials/SecretsGroups";
import { SecretsMissingBanner } from "@/components/credentials/SecretsMissingBanner";
import { isMissingHere, refsWaiting } from "@/components/credentials/secretRows";
import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { PageHeader } from "@/components/PageHeader";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import type { CredentialRef } from "@/lib/api/credentials";
import { translateApiError } from "@/lib/api/errors";
import { usePendingApprovals } from "@/lib/hooks/useApprovals";
import { useSecrets } from "@/lib/hooks/useSecrets";

type Open = { dialog: "add" | "scan" } | { dialog: SecretRowAction; row: CredentialRef } | null;

export function SecretsPage() {
  const { t } = useTranslation();
  const secrets = useSecrets();
  const approvals = usePendingApprovals();
  const waiting = refsWaiting(approvals.data?.approvals);
  const [query, setQuery] = useState("");
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
        icon={KeyRound}
        title={t("secrets.title")}
        badges={<HelpTip label={t("secrets.about.label")}>{t("secrets.about.body")}</HelpTip>}
        subtitle={t("secrets.subtitle")}
        actions={
          firstRun ? null : (
            <div className="flex flex-wrap items-center gap-2">
              <SearchInput
                value={query}
                onChange={setQuery}
                ariaLabel={t("secrets.search")}
                placeholder={t("secrets.search")}
                className="w-[220px]"
              />
              {scanButton}
              {addButton}
            </div>
          )
        }
      />

      <PendingApprovalsEntry />
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
          icon={KeyRound}
          title={t("secrets.empty.title")}
          description={t("secrets.empty.body")}
          action={addButton}
          secondaryAction={scanButton}
        />
      ) : (
        <SecretsGroups
          rows={rows}
          waiting={waiting}
          query={query}
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
