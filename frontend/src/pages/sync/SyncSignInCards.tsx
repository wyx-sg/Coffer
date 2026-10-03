// frontend/src/pages/sync/SyncSignInCards.tsx — the two problem cards about the push
// secret: the remote refused it (6.4.16) and it still waits for a person's
// approval (6.4.33). Neither has Retry or a hand-off: the fix is a choice
// the person makes in Secrets, and the header's Sync now runs the next round.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SyncProblem } from "@/lib/api/sync";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { SyncBannerCard } from "./SyncBanner";
import { Actions, Body, GitMessageDisclosure } from "./SyncProblemParts";

interface Props {
  problem: SyncProblem;
  host: string;
  onIgnore?: () => void;
}

function SecretName({ name }: { name: string }) {
  return (
    <>
      <code className="rounded-xs bg-code px-1 py-0.5 font-mono text-xs text-text">
        {name}
      </code>{" "}
    </>
  );
}

export function AuthFailedCard({ problem, host, onIgnore }: Props) {
  const { t } = useTranslation();
  return (
    <SyncBannerCard
      icon={KeyRound}
      tone="err"
      title={t("sync.problem.auth_failed.title")}
      onIgnore={onIgnore}
      testId="sync-problem"
    >
      <Body>
        {problem.secret_ref ? (
          <>
            <SecretName name={problem.secret_ref} />
            {t("sync.problem.auth_failed.body", { host })}
          </>
        ) : (
          t("sync.problem.auth_failed.bodyNoSecret", { host })
        )}
      </Body>
      <GitMessageDisclosure message={problem.message} />
      <Actions>
        <Button asChild variant="outline" size="sm">
          <Link to="/sync?tab=remote&focus=secret">{t("sync.problem.chooseSecret")}</Link>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link to="/secrets">{t("sync.problem.openSecrets")}</Link>
        </Button>
      </Actions>
    </SyncBannerCard>
  );
}

export function WaitingApprovalCard({ problem, host, onIgnore }: Props) {
  const { t } = useTranslation();
  return (
    <SyncBannerCard
      icon={KeyRound}
      tone="warn"
      title={t("sync.problem.waiting_approval.title")}
      onIgnore={onIgnore}
      testId="sync-problem"
    >
      <Body>
        {problem.secret_ref ? <SecretName name={problem.secret_ref} /> : null}
        {t("sync.problem.waiting_approval.body", { host })}
      </Body>
      <Actions>
        <Button type="button" variant="outline" size="sm" onClick={openApprovalsSheet}>
          {t("sync.problem.review")}
        </Button>
      </Actions>
    </SyncBannerCard>
  );
}
