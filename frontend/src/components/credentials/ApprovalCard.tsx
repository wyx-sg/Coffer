// src/components/credentials/ApprovalCard.tsx — one change waiting for approval, as a question with Reject and Approve.
//
// The question names the change and the secret ("Approve a new value for
// github-token?", "Approve the new secret npm-publish-token?"), then what
// holds meanwhile, then Change · Secret · Requested by · Used by (and, for a
// new use, where the secret would go). In the Coffer app Approve… runs the
// shell's presence check — Touch ID or the login password; in a browser it is
// disabled, naming the app, and only Reject works (spec secret "Show each
// change waiting for approval as the question it asks").
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Approval, CredentialRef } from "@/lib/api/credentials";
import { useApproveApproval, useRejectApproval } from "@/lib/hooks/useApprovals";
import { citersOf, displayName } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

interface Props {
  approval: Approval;
  /** The secret the approval names, from the list, for what uses it. */
  row: CredentialRef | undefined;
  /** Whether Approve can run here (the desktop shell). */
  inShell: boolean;
  /** Whether the card is the dialog's only one, and so owns its title. */
  heading: "title" | "card";
}

function clock(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

export function ApprovalCard({ approval: a, row, inShell, heading }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const kindLabel = useKindLabel();
  const reject = useRejectApproval();
  const approve = useApproveApproval();
  const busy = reject.isPending || approve.isPending;
  const name = row ? displayName(row) : (a.ref ?? "").replace(/^secret\//, "");
  const users = row ? citersOf(row).map((c) => `${kindLabel(c.kind)} ${c.name}`) : [];
  const destination = [a.destination_kind && kindLabel(a.destination_kind), a.destination_label]
    .filter(Boolean)
    .join(" ");
  const vars = { name, destination: a.destination_label ?? "", users: users.join(", ") };
  const where = t(`credentials.approvals.via.${a.requested_by}`, {
    defaultValue: a.requested_by,
  });

  const fields: [string, string | null][] = [
    [t("credentials.approvals.change"), t(`credentials.approvals.op.${a.op}`)],
    [t("credentials.approvals.secret"), a.ref ? name : null],
    [
      t("credentials.approvals.requestedBy"),
      t("credentials.approvals.requestedAt", {
        who: where,
        time: clock(a.created_at, i18n.language),
      }),
    ],
    [
      t("secrets.cols.usedBy"),
      a.op === "add_secret"
        ? t("credentials.approvals.nothingYet")
        : a.ref && a.op !== "bind"
          ? users.join(", ") || t("secrets.usedBy.nothing")
          : null,
    ],
    [
      t("credentials.approvals.destination"),
      destination ? (a.slot ? `${destination} (${a.slot})` : destination) : null,
    ],
    [t("credentials.approvals.target"), a.target],
  ];
  const question = t(`credentials.approvals.question.${a.op}`, vars);
  const body =
    a.op === "replace_value" && users.length === 0
      ? t("credentials.approvals.body.replace_value_unused")
      : t(`credentials.approvals.body.${a.op}`, vars);

  const onReject = () =>
    reject.mutate(a.id, {
      onSuccess: () => toast.success(t(`credentials.approvals.rejected.${a.op}`, vars)),
    });
  const onApprove = () =>
    approve.mutate(a.id, {
      onSuccess: () => toast.success(t(`credentials.approvals.approved.${a.op}`, vars)),
    });

  return (
    <li
      className="space-y-3 rounded-xl border border-border-subtle bg-surface-sunken p-3"
      data-testid="approval-row"
    >
      {heading === "card" ? <p className="text-sm font-semibold text-text">{question}</p> : null}
      <p className="text-xs text-text-muted">{body}</p>
      <dl className="grid grid-cols-[96px_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        {fields
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-text-muted">{label}</dt>
              <dd className="break-all text-text">{value}</dd>
            </div>
          ))}
      </dl>
      <div className="flex items-center gap-2">
        <p className="mr-auto text-2xs text-text-muted">
          {inShell ? t("credentials.approvals.hintShell") : t("credentials.approvals.openApp")}
        </p>
        <Button size="sm" variant="outline" disabled={busy} onClick={onReject}>
          {t("credentials.approvals.reject")}
        </Button>
        {inShell ? (
          <Button size="sm" disabled={busy} onClick={onApprove}>
            {t("credentials.approvals.approveEllipsis")}
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              {/* A disabled button fires no pointer events; the span carries the tooltip. */}
              <span tabIndex={0} title={t("credentials.approvals.approveInApp")}>
                <Button size="sm" disabled>
                  {t("credentials.approvals.approve")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{t("credentials.approvals.approveInApp")}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </li>
  );
}
